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
    return str(value)


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
    target_user = dsportal_text(request.get("schema_username") or "").strip().upper()

    if not source_user:
        dsportal_fail("Reference datasource %s does not expose a JDBC user property" % source_name)
    if not target_user:
        dsportal_fail("Target schema username is required")

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
    existing_names = set(
        [dsportal_text(ds.getName()).lower() for ds in (cmo.getJDBCSystemResources() or [])]
    )
    for item in plan["datasources"]:
        if item["target_name"].lower() in existing_names:
            item["status"] = "Already Exists"
        missing_targets = []
        for target_name in item["target_targets"]:
            if dsportal_target_mbean(target_name) is None:
                missing_targets.append(target_name)
        if missing_targets:
            item["status"] = "Invalid Target"
            item["missing_targets"] = missing_targets


def dsportal_create_datasource(item, password_pattern):
    name = item["target_name"]
    ds = cmo.createJDBCSystemResource(name)
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
    user_prop = props.createProperty("user")
    user_prop.setValue(item["target_user"])

    for prop_name in item["driver_properties"]:
        if prop_name.lower() == "user":
            continue
        prop = props.createProperty(prop_name)
        prop.setValue(item["driver_properties"][prop_name])

    oracle = resource.getJDBCOracleParams()
    if item.get("fan_enabled") or item.get("ons_nodes"):
        try:
            oracle.setFanEnabled(True)
        except:
            pass
    if item.get("ons_nodes"):
        try:
            oracle.setOnsNodeList(item["ons_nodes"])
        except:
            pass

    for target_name in item["target_targets"]:
        target = dsportal_target_mbean(target_name)
        if target is None:
            dsportal_fail("Target %s was not found while creating %s" % (target_name, name))
        ds.addTarget(target)


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
        if dsportal_matches_reference(ds, reference_entity, request["datasource_type"])
    ]

    if not matches:
        dsportal_fail(
            "No WebLogic datasources were found for reference entity %s"
            % reference_entity
        )

    plan = {
        "request_id": request["request_id"],
        "application": request["application"],
        "environment": request["environment"],
        "domain_name": request["domain_name"],
        "action": action,
        "datasource_type": request["datasource_type"],
        "reference_entity": reference_entity,
        "target_entity": target_entity,
        "datasources": [
            dsportal_capture_reference(ds, reference_entity, target_entity, request)
            for ds in matches
        ],
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
                "Apply blocked because one or more target datasources already exist or reference invalid targets"
            )

        edit()
        startEdit()
        try:
            cd("/")
            for item in plan["datasources"]:
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
    ready = [
        item["target_name"]
        for item in plan["datasources"]
        if item.get("status") == "Ready"
    ]
    plan["summary"] = {
        "total": len(plan["datasources"]),
        "created_count": len(created),
        "created_names": created,
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
