# WLST/Jython script. Keep Python 2.7-compatible syntax for WebLogic installations.
import json
import os
import re
import sys
import traceback

try:
    import jarray
    from java.lang import String
except Exception:
    jarray = None
    String = None


def dsportal_fail(message):
    raise RuntimeError(message)


def dsportal_text(value):
    if value is None:
        return ""
    return "%s" % value


def dsportal_replace_entity(value, reference_entity, target_entity):
    if value is None:
        return value
    # Entity codes in current datasource naming conventions occur at the end
    # of a name or immediately before a suffix such as _GTXN / _XA. Restrict
    # replacement to that position so short codes such as IN or AE do not
    # modify unrelated dsportal_text.
    return re.sub(
        re.escape(reference_entity) + r"(?=$|_)",
        target_entity,
        dsportal_text(value),
        flags=re.IGNORECASE,
    )


def dsportal_read_property(driver_params, name):
    try:
        prop = driver_params.getProperties().lookupProperty(name)
        return dsportal_text(prop.getValue()) if prop else ""
    except Exception:
        return ""


def dsportal_bean_value(bean, name, default=None):
    # WLST exposes some Java proxy attributes through getX() and boolean
    # attributes through isX(). On some Jython/WebLogic combinations a missing
    # proxy method raises a Java-backed AttributeError that does not reliably
    # match "except Exception", so use bare except for this compatibility shim.
    try:
        getter = getattr(bean, "get" + name)
        return getter()
    except:
        try:
            getter = getattr(bean, "is" + name)
            return getter()
        except:
            return default


def dsportal_capture_attributes(bean, names):
    values = {}
    for name in names:
        value = dsportal_bean_value(bean, name, None)
        if value is not None:
            values[name] = value
    return values


def dsportal_apply_attributes(bean, values):
    for name in values:
        try:
            setter = getattr(bean, "set" + name)
            setter(values[name])
        except Exception:
            # Different WebLogic releases expose slightly different optional
            # tuning attributes. Required connection settings are configured
            # separately below.
            pass


POOL_ATTRIBUTES = [
    "InitialCapacity",
    "MinCapacity",
    "MaxCapacity",
    "CapacityIncrement",
    "ConnectionCreationRetryFrequencySeconds",
    "ConnectionReserveTimeoutSeconds",
    "TestFrequencySeconds",
    "TestConnectionsOnReserve",
    "TestTableName",
    "SecondsToTrustAnIdlePoolConnection",
    "ShrinkFrequencySeconds",
    "InactiveConnectionTimeoutSeconds",
    "StatementTimeout",
    "StatementCacheSize",
    "StatementCacheType",
    "RemoveInfectedConnections",
    "PinnedToThread",
]

DATASOURCE_ATTRIBUTES = [
    "GlobalTransactionsProtocol",
    "KeepConnAfterLocalTx",
    "KeepConnAfterGlobalTx",
    "RowPrefetch",
    "RowPrefetchSize",
    "StreamChunkSize",
]


def dsportal_java_string_array(values):
    if jarray is None:
        return values
    return jarray.array([String(dsportal_text(value)) for value in values], String)


def dsportal_capture_reference(ds, reference_entity, target_entity, request):
    resource = ds.getJDBCResource()
    params = resource.getJDBCDataSourceParams()
    driver = resource.getJDBCDriverParams()
    pool = resource.getJDBCConnectionPoolParams()
    oracle = resource.getJDBCOracleParams()

    source_name = dsportal_text(ds.getName())
    target_name = dsportal_replace_entity(source_name, reference_entity, target_entity)
    jndis = [dsportal_text(value) for value in (params.getJNDINames() or [])]
    target_jndis = [
        dsportal_replace_entity(value, reference_entity, target_entity)
        for value in jndis
    ]
    source_user = dsportal_read_property(driver, "user")

    if not source_user:
        dsportal_fail("Reference datasource %s does not expose a JDBC user property" % source_name)

    # Derive each target schema from the live reference datasource.
    # This works for both single-schema applications (for example OBPUS ->
    # OBPIN) and applications with multiple datasource-specific schemas.
    target_user = dsportal_replace_entity(
        source_user,
        reference_entity,
        target_entity,
    ).upper()

    if not target_user or target_user == source_user.upper():
        dsportal_fail(
            "Unable to derive target schema user from %s using reference entity %s"
            % (source_user, reference_entity)
        )

    if request["datasource_type"] == "gridlink":
        target_url = (
            "jdbc:oracle:thin:@(DESCRIPTION="
            "(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(HOST=%s)(PORT=%s)))"
            "(CONNECT_DATA=(SERVICE_NAME=%s)))"
            % (
                request["db_host"],
                request["db_port"],
                request["service_id"],
            )
        )
    else:
        target_url = "jdbc:oracle:thin:@//%s:%s/%s" % (
            request["db_host"],
            request["db_port"],
            request["service_id"],
        )

    source_targets = [dsportal_text(target.getName()) for target in (ds.getTargets() or [])]
    target_targets = [
        dsportal_replace_entity(value, reference_entity, target_entity)
        for value in source_targets
    ]

    properties = {}
    try:
        for prop in driver.getProperties().getProperties():
            prop_name = dsportal_text(prop.getName())
            if prop_name.lower() != "user":
                properties[prop_name] = dsportal_text(prop.getValue())
    except Exception:
        pass

    ons_nodes = dsportal_text(request.get("ons_nodes") or "")
    source_ons = dsportal_text(dsportal_bean_value(oracle, "OnsNodeList", "") or "")
    fan_value = dsportal_bean_value(oracle, "FanEnabled", False)
    fan_enabled = dsportal_text(fan_value).strip().lower() in ("true", "1", "yes")

    return {
        "source_name": source_name,
        "target_name": target_name,
        "source_jndis": jndis,
        "target_jndis": target_jndis,
        "source_user": source_user,
        "target_user": target_user,
        "source_url": dsportal_text(driver.getUrl()),
        "target_url": target_url,
        "driver_name": dsportal_text(driver.getDriverName()),
        "datasource_type": request["datasource_type"],
        "datasource_attributes": dsportal_capture_attributes(params, DATASOURCE_ATTRIBUTES),
        "pool_attributes": dsportal_capture_attributes(pool, POOL_ATTRIBUTES),
        "driver_properties": properties,
        "source_targets": source_targets,
        "target_targets": target_targets,
        "fan_enabled": fan_enabled,
        "ons_nodes": ons_nodes or source_ons,
        "status": "Ready",
    }


def dsportal_is_gridlink(ds):
    try:
        oracle = ds.getJDBCResource().getJDBCOracleParams()
        fan_value = dsportal_bean_value(oracle, "FanEnabled", False)
        fan_enabled = dsportal_text(fan_value).strip().lower() in ("true", "1", "yes")
        ons_nodes = dsportal_text(dsportal_bean_value(oracle, "OnsNodeList", "") or "").strip()
        return fan_enabled or ons_nodes != ""
    except:
        return False


def dsportal_matches_reference(ds, reference_entity, datasource_type):
    # Discover entity-specific datasources dynamically from live WebLogic.
    # Match the exact entity suffix in datasource name, JNDI or schema user.
    # The suffix boundary prevents IN from matching INGC.
    if datasource_type == "gridlink" and not dsportal_is_gridlink(ds):
        return False
    if datasource_type == "standalone" and dsportal_is_gridlink(ds):
        return False

    token = re.compile(
        re.escape(reference_entity) + r"(?=$|_)",
        flags=re.IGNORECASE,
    )
    name = dsportal_text(ds.getName())
    if token.search(name):
        return True
    try:
        resource = ds.getJDBCResource()
        for jndi in resource.getJDBCDataSourceParams().getJNDINames() or []:
            if token.search(dsportal_text(jndi)):
                return True
        username = dsportal_read_property(resource.getJDBCDriverParams(), "user")
        if username and token.search(username):
            return True
    except Exception:
        pass
    return False


def dsportal_target_mbean(name):
    value = getMBean("/Clusters/" + name)
    if value is not None:
        return value
    value = getMBean("/Servers/" + name)
    if value is not None:
        return value
    return getMBean("/MigratableTargets/" + name)


def dsportal_validate_plan(plan):
    # Avoid Python's set() name because WLST defines its own set() command.
    existing_names = {}
    for ds in (cmo.getJDBCSystemResources() or []):
        existing_names[dsportal_text(ds.getName()).lower()] = True

    allow_update = plan.get("update_existing") is True

    for item in plan["datasources"]:
        if item["target_name"].lower() in existing_names:
            if allow_update:
                item["status"] = "Ready"
                item["change_type"] = "Update"
            else:
                item["status"] = "Already Exists"
                item["change_type"] = "Create"
        else:
            item["change_type"] = "Create"

        missing_targets = []
        for target_name in item["target_targets"]:
            if dsportal_target_mbean(target_name) is None:
                missing_targets.append(target_name)
        if missing_targets:
            item["status"] = "Invalid Target"
            item["missing_targets"] = missing_targets


def dsportal_find_datasource(name):
    wanted = name.lower()
    for ds in (cmo.getJDBCSystemResources() or []):
        if dsportal_text(ds.getName()).lower() == wanted:
            return ds
    return None


def dsportal_configure_datasource(ds, item, password_pattern, replace_targets):
    name = item["target_name"]
    resource = ds.getJDBCResource()
    resource.setName(name)

    params = resource.getJDBCDataSourceParams()
    params.setJNDINames(dsportal_java_string_array(item["target_jndis"]))
    dsportal_apply_attributes(params, item["datasource_attributes"])

    pool = resource.getJDBCConnectionPoolParams()
    dsportal_apply_attributes(pool, item["pool_attributes"])

    driver = resource.getJDBCDriverParams()
    driver.setDriverName(item["driver_name"])
    driver.setUrl(item["target_url"])

    password = password_pattern
    password = password.replace("{{username}}", item["target_user"])
    password = password.replace("{username}", item["target_user"])
    driver.setPassword(password)

    props = driver.getProperties()
    user_prop = props.lookupProperty("user")
    if user_prop is None:
        user_prop = props.createProperty("user")
    user_prop.setValue(item["target_user"])

    for prop_name in item["driver_properties"]:
        if prop_name.lower() == "user":
            continue
        prop = props.lookupProperty(prop_name)
        if prop is None:
            prop = props.createProperty(prop_name)
        prop.setValue(item["driver_properties"][prop_name])

    # FAN and ONS are GridLink-only settings. For standalone
    # datasources do not touch JDBCOracleParams at all; this preserves any
    # existing values during updates and avoids unnecessary activation changes.
    if item.get("datasource_type") == "gridlink":
        ons_nodes = dsportal_text(item.get("ons_nodes") or "").strip()
        if not ons_nodes:
            dsportal_fail("ONS nodes are required for GridLink datasource %s" % name)

        oracle = resource.getJDBCOracleParams()
        try:
            oracle.setFanEnabled(True)
        except:
            pass
        try:
            oracle.setOnsNodeList(ons_nodes)
        except:
            pass

    if replace_targets:
        for current_target in (ds.getTargets() or []):
            try:
                ds.removeTarget(current_target)
            except:
                pass

    for target_name in item["target_targets"]:
        target = dsportal_target_mbean(target_name)
        if target is None:
            dsportal_fail("Target %s was not found while configuring %s" % (target_name, name))
        already_targeted = False
        for current_target in (ds.getTargets() or []):
            if dsportal_text(current_target.getName()) == target_name:
                already_targeted = True
                break
        if not already_targeted:
            ds.addTarget(target)


def dsportal_update_datasource(item, password_pattern):
    ds = dsportal_find_datasource(item["target_name"])
    if ds is None:
        dsportal_fail("Existing datasource %s was not found for update" % item["target_name"])
    dsportal_configure_datasource(ds, item, password_pattern, True)


def dsportal_create_datasource(item, password_pattern):
    name = item["target_name"]
    ds = cmo.createJDBCSystemResource(name)
    dsportal_configure_datasource(ds, item, password_pattern, False)


def dsportal_main():
    if len(sys.argv) != 4:
        dsportal_fail(
            "Usage: weblogic_datasource_manager.py <request.json> <plan.json> <action>"
        )

    request_path = sys.argv[1]
    plan_path = sys.argv[2]
    action = sys.argv[3].lower()

    with open(request_path, "r") as handle:
        request = json.load(handle)

    if action not in ("preview", "apply"):
        dsportal_fail("Action must be preview or apply")

    admin_url = "t3://%s:%s" % (request["admin_host"], request["admin_port"])
    connect(request["weblogic_username"], request["weblogic_password"], admin_url)
    domainConfig()

    reference_entity = request["reference_entity"].upper()
    target_entity = request["target_entity"].upper()
    matches = [
        ds
        for ds in (cmo.getJDBCSystemResources() or [])
        if dsportal_matches_reference(
            ds,
            reference_entity,
            request["datasource_type"],
        )
    ]

    if not matches:
        dsportal_fail(
            "No WebLogic datasources were found for reference entity %s"
            % reference_entity
        )

    datasource_items = [
        dsportal_capture_reference(ds, reference_entity, target_entity, request)
        for ds in matches
    ]

    # Existing targets are updates; missing targets are creates.
    # This behavior is application-agnostic and is determined entirely from
    # the live WebLogic reference entity and current target state.
    update_existing = True

    plan = {
        "request_id": request["request_id"],
        "application": request["application"],
        "environment": request["environment"],
        "domain_name": request["domain_name"],
        "action": action,
        "datasource_type": request["datasource_type"],
        "reference_entity": reference_entity,
        "target_entity": target_entity,
        "update_existing": update_existing,
        "datasources": datasource_items,
    }

    dsportal_validate_plan(plan)

    if action == "apply":
        blocked = [
            item
            for item in plan["datasources"]
            if item["status"] != "Ready"
        ]
        if blocked:
            dsportal_fail(
                "Apply blocked because one or more datasource changes are not ready or reference invalid targets"
            )

        edit()
        startEdit()
        try:
            cd("/")
            for item in plan["datasources"]:
                if item.get("change_type") == "Update":
                    dsportal_update_datasource(item, request["password_pattern"])
                    item["status"] = "Updated"
                else:
                    dsportal_create_datasource(item, request["password_pattern"])
                    item["status"] = "Created"
            save()
            activate(block="true")
        except Exception:
            try:
                undo(defaultAnswer="y")
                cancelEdit("y")
            except Exception:
                pass
            raise

    created = [
        item["target_name"]
        for item in plan["datasources"]
        if item.get("status") == "Created"
    ]
    updated = [
        item["target_name"]
        for item in plan["datasources"]
        if item.get("status") == "Updated"
    ]
    ready = [
        item["target_name"]
        for item in plan["datasources"]
        if item.get("status") == "Ready"
    ]
    plan["summary"] = {
        "total": len(plan["datasources"]),
        "created_count": len(created),
        "created_names": created,
        "updated_count": len(updated),
        "updated_names": updated,
        "ready_count": len(ready),
    }

    with open(plan_path, "w") as handle:
        json.dump(plan, handle, indent=2)

    disconnect()
    print(
        "Datasource %s completed request_id=%s reference=%s target=%s count=%s"
        % (
            action,
            request["request_id"],
            reference_entity,
            target_entity,
            len(plan["datasources"]),
        )
    )


try:
    dsportal_main()
except Exception:
    traceback.print_exc()
    try:
        disconnect()
    except Exception:
        pass
    raise
