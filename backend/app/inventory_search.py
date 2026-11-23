from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from .inventory_microservices import InventoryMsConfiguration, InventoryMsGroup, InventoryMsService
from .inventory_patching import InventoryPatchActivity, InventoryPatchingAsset, sync_all_gtb_records
from .inventory_store import InventoryApplication, InventoryEnvironment, InventoryRecord
from .user_store import session_factory


def search_inventory(query_text: str, limit: int = 50) -> dict[str, Any]:
    text = str(query_text or "").strip()
    if len(text) < 2:
        return {"query": text, "total": 0, "gtb": [], "microservices": [], "patching": []}

    token = f"%{text}%"
    factory = session_factory()

    with factory() as db:
        gtb_rows = db.execute(
            select(InventoryRecord, InventoryApplication, InventoryEnvironment)
            .join(InventoryApplication, InventoryApplication.id == InventoryRecord.application_id)
            .join(InventoryEnvironment, InventoryEnvironment.id == InventoryRecord.environment_id)
            .where(
                InventoryRecord.is_active == 1,
                InventoryApplication.category == "GTB",
                or_(
                    InventoryRecord.ip_address.like(token),
                    InventoryRecord.hostname.like(token),
                    InventoryRecord.asset_type.like(token),
                    InventoryRecord.app_name.like(token),
                    InventoryRecord.ssh_username.like(token),
                    InventoryRecord.application_username.like(token),
                    InventoryRecord.console_details.like(token),
                    InventoryRecord.notes.like(token),
                    InventoryApplication.code.like(token),
                    InventoryApplication.display_name.like(token),
                    InventoryEnvironment.code.like(token),
                    InventoryEnvironment.display_name.like(token),
                ),
            )
            .order_by(InventoryApplication.display_name, InventoryEnvironment.sort_order, InventoryRecord.hostname)
            .limit(limit)
        ).all()
        gtb = [
            {
                "id": record.id,
                "application_id": app.id,
                "application": app.display_name,
                "environment": env.display_name,
                "ip_address": record.ip_address or "",
                "hostname": record.hostname or "",
                "asset_type": record.asset_type or "",
                "app_name": record.app_name or "",
                "console_details": record.console_details or "",
            }
            for record, app, env in gtb_rows
        ]

        ms_rows = db.execute(
            select(InventoryMsConfiguration, InventoryMsService, InventoryMsGroup, InventoryEnvironment)
            .join(InventoryMsService, InventoryMsService.id == InventoryMsConfiguration.service_id)
            .join(InventoryMsGroup, InventoryMsGroup.id == InventoryMsService.group_id)
            .join(InventoryEnvironment, InventoryEnvironment.id == InventoryMsConfiguration.environment_id)
            .where(
                InventoryMsConfiguration.is_active == 1,
                InventoryMsService.is_active == 1,
                InventoryMsGroup.is_active == 1,
                or_(
                    InventoryMsGroup.code.like(token),
                    InventoryMsGroup.display_name.like(token),
                    InventoryMsService.code.like(token),
                    InventoryMsService.display_name.like(token),
                    InventoryEnvironment.code.like(token),
                    InventoryEnvironment.display_name.like(token),
                    InventoryMsConfiguration.connection_name.like(token),
                    InventoryMsConfiguration.db_url.like(token),
                    InventoryMsConfiguration.db_name.like(token),
                    InventoryMsConfiguration.db_username.like(token),
                    InventoryMsConfiguration.notes.like(token),
                ),
            )
            .order_by(InventoryMsGroup.display_name, InventoryMsService.display_name, InventoryEnvironment.sort_order)
            .limit(limit)
        ).all()
        microservices = [
            {
                "id": config.id,
                "group_id": group.id,
                "group": group.display_name,
                "service_id": service.id,
                "service": service.display_name,
                "environment": env.display_name,
                "connection_name": config.connection_name,
                "db_url": config.db_url or "",
                "db_name": config.db_name or "",
                "db_username": config.db_username or "",
            }
            for config, service, group, env in ms_rows
        ]

    sync_all_gtb_records("system")

    with factory() as db:
        patch_rows = list(
            db.scalars(
                select(InventoryPatchingAsset)
                .where(
                    InventoryPatchingAsset.is_active == 1,
                    or_(
                        InventoryPatchingAsset.asset_identifier.like(token),
                        InventoryPatchingAsset.hostname.like(token),
                        InventoryPatchingAsset.application.like(token),
                        InventoryPatchingAsset.application_owner.like(token),
                        InventoryPatchingAsset.asset_type.like(token),
                        InventoryPatchingAsset.environment_name.like(token),
                    ),
                )
                .order_by(InventoryPatchingAsset.application, InventoryPatchingAsset.hostname)
                .limit(limit)
            ).all()
        )

        patching = []
        for asset in patch_rows:
            activity = db.scalar(
                select(InventoryPatchActivity)
                .where(InventoryPatchActivity.patching_asset_id == asset.id)
                .order_by(InventoryPatchActivity.updated_at.desc())
            )
            patching.append(
                {
                    "id": asset.id,
                    "asset_identifier": asset.asset_identifier,
                    "hostname": asset.hostname or "",
                    "application": asset.application or "",
                    "application_owner": asset.application_owner or "",
                    "asset_type": asset.asset_type or "",
                    "environment_name": asset.environment_name or "",
                    "environment_class": asset.environment_class,
                    "source_type": asset.source_type,
                    "status": activity.status if activity else "NOT_STARTED",
                    "cr_number": activity.cr_number or "" if activity else "",
                    "planned_date": activity.planned_date.isoformat() if activity and activity.planned_date else "",
                    "comments": activity.comments or "" if activity else "",
                }
            )

        # Also find patching assets by CR/status/comments when the static asset fields did not match.
        activity_matches = db.execute(
            select(InventoryPatchingAsset, InventoryPatchActivity)
            .join(InventoryPatchActivity, InventoryPatchActivity.patching_asset_id == InventoryPatchingAsset.id)
            .where(
                InventoryPatchingAsset.is_active == 1,
                or_(
                    InventoryPatchActivity.status.like(token),
                    InventoryPatchActivity.cr_number.like(token),
                    InventoryPatchActivity.app_team_approval.like(token),
                    InventoryPatchActivity.comments.like(token),
                    InventoryPatchActivity.patch_role.like(token),
                ),
            )
            .order_by(InventoryPatchActivity.updated_at.desc())
            .limit(limit)
        ).all()
        existing_ids = {item["id"] for item in patching}
        for asset, activity in activity_matches:
            if asset.id in existing_ids:
                continue
            patching.append(
                {
                    "id": asset.id,
                    "asset_identifier": asset.asset_identifier,
                    "hostname": asset.hostname or "",
                    "application": asset.application or "",
                    "application_owner": asset.application_owner or "",
                    "asset_type": asset.asset_type or "",
                    "environment_name": asset.environment_name or "",
                    "environment_class": asset.environment_class,
                    "source_type": asset.source_type,
                    "status": activity.status,
                    "cr_number": activity.cr_number or "",
                    "planned_date": activity.planned_date.isoformat() if activity.planned_date else "",
                    "comments": activity.comments or "",
                }
            )
            if len(patching) >= limit:
                break

    return {
        "query": text,
        "total": len(gtb) + len(microservices) + len(patching),
        "gtb": gtb,
        "microservices": microservices,
        "patching": patching,
    }
