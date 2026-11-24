import { FormEvent, useEffect, useMemo, useState } from "react";
import { Archive, History, Pencil, Plus, RotateCcw, Search, X } from "lucide-react";
import {
  archiveInventoryItem,
  createInventoryItem,
  getInventoryHistory,
  getInventoryItemHistory,
  getInventoryItems,
  getInventorySummary,
  getInventoryTypes,
  restoreInventoryItem,
  updateInventoryItem,
} from "../services/api";
import type { InventoryAuditEvent, InventoryItem, InventorySummary, InventoryTypeOption } from "../types";

type PropertyRow = { key: string; value: string };
type InventoryForm = {
  item_type: string;
  name: string;
  code: string;
  description: string;
  parent_id: string;
  source_system: string;
  properties: PropertyRow[];
};

const emptySummary: InventorySummary = { total: 0, active: 0, archived: 0, by_type: {} };
const emptyForm = (): InventoryForm => ({
  item_type: "environment",
  name: "",
  code: "",
  description: "",
  parent_id: "",
  source_system: "manual",
  properties: [],
});

function propertiesFromItem(item: InventoryItem): PropertyRow[] {
  return Object.entries(item.details ?? {}).map(([key, value]) => ({
    key,
    value: typeof value === "string" ? value : JSON.stringify(value),
  }));
}

function detailsFromRows(rows: PropertyRow[]): Record<string, string> {
  return rows.reduce<Record<string, string>>((acc, row) => {
    const key = row.key.trim();
    if (key) acc[key] = row.value.trim();
    return acc;
  }, {});
}

function formatValue(value?: string | null) {
  if (value === null || value === undefined || value === "") return "—";
  try {
    const parsed = JSON.parse(value);
    if (typeof parsed === "object") return JSON.stringify(parsed);
    return String(parsed);
  } catch {
    return value;
  }
}

function prettyType(value: string, types: InventoryTypeOption[]) {
  return types.find((item) => item.value === value)?.label ?? value.replaceAll("_", " ");
}

export default function InventoryPage({ token }: { token: string }) {
  const [types, setTypes] = useState<InventoryTypeOption[]>([]);
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [referenceItems, setReferenceItems] = useState<InventoryItem[]>([]);
  const [summary, setSummary] = useState<InventorySummary>(emptySummary);
  const [tab, setTab] = useState<"inventory" | "history">("inventory");
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [auditQuery, setAuditQuery] = useState("");
  const [auditActor, setAuditActor] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditType, setAuditType] = useState("");
  const [audit, setAudit] = useState<InventoryAuditEvent[]>([]);
  const [editing, setEditing] = useState<InventoryItem | null>(null);
  const [form, setForm] = useState<InventoryForm>(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [historyItem, setHistoryItem] = useState<InventoryItem | null>(null);
  const [itemHistory, setItemHistory] = useState<InventoryAuditEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const activeParents = useMemo(
    () => referenceItems.filter((item) => item.is_active && item.id !== editing?.id),
    [referenceItems, editing]
  );

  async function refreshReferenceData() {
    const [nextSummary, nextItems] = await Promise.all([
      getInventorySummary(token),
      getInventoryItems(token, { include_inactive: false }),
    ]);
    setSummary(nextSummary);
    setReferenceItems(nextItems);
  }

  useEffect(() => {
    getInventoryTypes(token).then(setTypes).catch((e) => setError(e instanceof Error ? e.message : "Unable to load inventory types"));
    void refreshReferenceData();
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      getInventoryItems(token, {
        q: query,
        item_type: typeFilter,
        include_inactive: includeArchived,
      })
        .then(setItems)
        .catch((e) => setError(e instanceof Error ? e.message : "Unable to load inventory"));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [token, query, typeFilter, includeArchived]);

  useEffect(() => {
    if (tab !== "history") return;
    const timer = window.setTimeout(() => {
      getInventoryHistory(
        token,
        { q: auditQuery, actor: auditActor, action: auditAction, item_type: auditType, limit: 500 }
      )
        .then(setAudit)
        .catch((e) => setError(e instanceof Error ? e.message : "Unable to load inventory history"));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [token, tab, auditQuery, auditActor, auditAction, auditType]);

  async function reloadItems() {
    const nextItems = await getInventoryItems(token, {
      q: query,
      item_type: typeFilter,
      include_inactive: includeArchived,
    });
    setItems(nextItems);
    await refreshReferenceData();
  }

  function openCreate() {
    setEditing(null);
    setForm(emptyForm());
    setError("");
    setNotice("");
    setShowForm(true);
  }

  function openEdit(item: InventoryItem) {
    setEditing(item);
    setForm({
      item_type: item.item_type,
      name: item.name,
      code: item.code,
      description: item.description,
      parent_id: item.parent_id ? String(item.parent_id) : "",
      source_system: item.source_system,
      properties: propertiesFromItem(item),
    });
    setError("");
    setNotice("");
    setShowForm(true);
  }

  function updateProperty(index: number, patch: Partial<PropertyRow>) {
    setForm((current) => ({
      ...current,
      properties: current.properties.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row),
    }));
  }

  function removeProperty(index: number) {
    setForm((current) => ({
      ...current,
      properties: current.properties.filter((_, rowIndex) => rowIndex !== index),
    }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const payload = {
      item_type: form.item_type,
      name: form.name.trim(),
      code: form.code.trim(),
      description: form.description.trim(),
      parent_id: form.parent_id ? Number(form.parent_id) : null,
      source_system: form.source_system.trim() || "manual",
      details: detailsFromRows(form.properties),
    };
    try {
      if (editing) {
        await updateInventoryItem(editing.id, payload, token);
        setNotice(`${form.name} updated successfully.`);
      } else {
        await createInventoryItem(payload, token);
        setNotice(`${form.name} added to inventory.`);
      }
      setShowForm(false);
      setEditing(null);
      await reloadItems();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save inventory item");
    } finally {
      setBusy(false);
    }
  }

  async function remove(item: InventoryItem) {
    if (!window.confirm(`Remove ${item.name} from active inventory? Its history will be preserved and it can be restored later.`)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await archiveInventoryItem(item.id, token);
      setNotice(`${item.name} removed from active inventory. History has been preserved.`);
      await reloadItems();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to remove inventory item");
    } finally {
      setBusy(false);
    }
  }

  async function restore(item: InventoryItem) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await restoreInventoryItem(item.id, token);
      setNotice(`${item.name} restored to active inventory.`);
      await reloadItems();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to restore inventory item");
    } finally {
      setBusy(false);
    }
  }

  async function openHistory(item: InventoryItem) {
    setHistoryItem(item);
    setItemHistory([]);
    setError("");
    try {
      setItemHistory(await getInventoryItemHistory(item.id, token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load item history");
    }
  }

  const topCounts = [
    ["Active", summary.active],
    ["Environments", summary.by_type.environment ?? 0],
    ["Services", summary.by_type.service ?? 0],
    ["Servers", summary.by_type.server ?? 0],
    ["Archived", summary.archived],
  ] as const;

  return (
    <section className="inventory-page">
      <div className="section-heading inventory-heading">
        <div>
          <span className="eyebrow">DEVOPS INVENTORY</span>
          <h2>Inventory Management</h2>
          <p>Manage environments, groups, applications, services, servers and related inventory with a complete audit trail.</p>
        </div>
        {tab === "inventory" && <button className="primary-button inventory-add-button" onClick={openCreate}><Plus size={17}/> Add Inventory</button>}
      </div>

      {error && <div className="form-error">{error}</div>}
      {notice && <div className="form-success inventory-notice">{notice}</div>}

      <div className="inventory-summary-grid">
        {topCounts.map(([label, value]) => <div className="inventory-stat" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>

      <div className="inventory-tabs">
        <button className={tab === "inventory" ? "active" : ""} onClick={() => setTab("inventory")}>Inventory</button>
        <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}><History size={16}/> Audit History</button>
      </div>

      {tab === "inventory" ? (
        <>
          <div className="inventory-filters">
            <label className="inventory-search"><Search size={17}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search IP, hostname, application, server, service..." /></label>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
              <option value="">All inventory types</option>
              {types.map((type) => <option value={type.value} key={type.value}>{type.label}</option>)}
            </select>
            <label className="inventory-check"><input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)}/> Show archived</label>
          </div>

          <div className="table-card inventory-table-card">
            <table>
              <thead><tr><th>Type</th><th>Name</th><th>Parent / Group</th><th>Properties</th><th>Source</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className={!item.is_active ? "inventory-archived-row" : ""}>
                    <td><span className="inventory-type-badge">{prettyType(item.item_type, types)}</span></td>
                    <td><strong>{item.name}</strong>{item.code && <small className="inventory-code">{item.code}</small>}{item.description && <small className="inventory-description">{item.description}</small>}</td>
                    <td>{item.parent_name ?? "—"}</td>
                    <td>
                      <div className="inventory-properties">
                        {Object.entries(item.details ?? {}).slice(0, 4).map(([key, value]) => <span key={key}><b>{key}</b>: {String(value)}</span>)}
                        {Object.keys(item.details ?? {}).length === 0 && <span className="inventory-muted">—</span>}
                        {Object.keys(item.details ?? {}).length > 4 && <span>+{Object.keys(item.details).length - 4} more</span>}
                      </div>
                    </td>
                    <td>{item.source_system}</td>
                    <td><span className={`inventory-status ${item.is_active ? "active" : "archived"}`}>{item.is_active ? "Active" : "Archived"}</span></td>
                    <td><small>{new Date(item.updated_at).toLocaleString()}<br/>{item.updated_by}</small></td>
                    <td>
                      <div className="inventory-actions">
                        <button className="secondary-button compact-button" onClick={() => openHistory(item)}><History size={14}/> History</button>
                        {item.is_active ? (
                          <>
                            <button className="secondary-button compact-button" onClick={() => openEdit(item)}><Pencil size={14}/> Edit</button>
                            <button className="danger-button compact-button" disabled={busy} onClick={() => remove(item)}><Archive size={14}/> Remove</button>
                          </>
                        ) : (
                          <button className="secondary-button compact-button" disabled={busy} onClick={() => restore(item)}><RotateCcw size={14}/> Restore</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {items.length === 0 && <tr><td colSpan={8} className="inventory-empty">No inventory records match the current filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="inventory-filters inventory-history-filters">
            <label className="inventory-search"><Search size={17}/><input value={auditQuery} onChange={(e) => setAuditQuery(e.target.value)} placeholder="Search item, field, old/new value..." /></label>
            <input value={auditActor} onChange={(e) => setAuditActor(e.target.value)} placeholder="Changed by" />
            <select value={auditType} onChange={(e) => setAuditType(e.target.value)}>
              <option value="">All inventory types</option>
              {types.map((type) => <option value={type.value} key={type.value}>{type.label}</option>)}
            </select>
            <select value={auditAction} onChange={(e) => setAuditAction(e.target.value)}>
              <option value="">All actions</option>
              <option value="CREATE">Created</option>
              <option value="UPDATE">Updated</option>
              <option value="ARCHIVE">Removed / Archived</option>
              <option value="RESTORE">Restored</option>
            </select>
          </div>
          <div className="table-card inventory-table-card">
            <table>
              <thead><tr><th>Date / Time</th><th>Item</th><th>Action</th><th>Field</th><th>Old Value</th><th>New Value</th><th>Changed By</th><th>Source</th></tr></thead>
              <tbody>
                {audit.map((event) => (
                  <tr key={event.id}>
                    <td><small>{new Date(event.changed_at).toLocaleString()}</small></td>
                    <td><strong>{event.item_name}</strong><small className="inventory-code">{prettyType(event.item_type, types)}</small></td>
                    <td><span className={`inventory-audit-action ${event.action.toLowerCase()}`}>{event.action}</span></td>
                    <td>{event.field_name ?? "—"}</td>
                    <td className="inventory-audit-value">{formatValue(event.old_value)}</td>
                    <td className="inventory-audit-value">{formatValue(event.new_value)}</td>
                    <td>{event.changed_by}</td>
                    <td>{event.source}</td>
                  </tr>
                ))}
                {audit.length === 0 && <tr><td colSpan={8} className="inventory-empty">No audit history matches the current filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {showForm && (
        <div className="modal-backdrop">
          <form className="modal-card inventory-modal" onSubmit={save}>
            <button type="button" className="modal-close" onClick={() => setShowForm(false)}><X size={18}/></button>
            <div>
              <span className="eyebrow">{editing ? "EDIT INVENTORY" : "ADD INVENTORY"}</span>
              <h3>{editing ? `Update ${editing.name}` : "Add Inventory Item"}</h3>
              <p>Use properties for searchable details such as IP address, hostname, owner, OS, namespace, URL or port.</p>
            </div>
            <div className="inventory-form-grid">
              <label>Type<select required value={form.item_type} onChange={(e) => setForm({ ...form, item_type: e.target.value })}>{types.map((type) => <option value={type.value} key={type.value}>{type.label}</option>)}</select></label>
              <label>Name<input required maxLength={255} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. UAT, H2H1CMUWSDSRV, payment-service" /></label>
              <label>Code / Identifier<input maxLength={128} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="Optional short code / asset ID" /></label>
              <label>Parent / Group<select value={form.parent_id} onChange={(e) => setForm({ ...form, parent_id: e.target.value })}><option value="">No parent</option>{activeParents.map((item) => <option key={item.id} value={item.id}>{prettyType(item.item_type, types)} — {item.name}</option>)}</select></label>
              <label>Source System<input maxLength={64} value={form.source_system} onChange={(e) => setForm({ ...form, source_system: e.target.value })} placeholder="manual / GTB / patching / microservices" /></label>
              <label className="inventory-description-field">Description<textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
            </div>
            <div className="inventory-property-editor">
              <div className="inventory-property-header"><div><strong>Properties</strong><small>These fields are searchable. Example: hostname, ip_address, application_owner, os, namespace.</small></div><button type="button" className="secondary-button compact-button" onClick={() => setForm((current) => ({ ...current, properties: [...current.properties, { key: "", value: "" }] }))}><Plus size={14}/> Add property</button></div>
              {form.properties.map((row, index) => (
                <div className="inventory-property-row" key={index}>
                  <input value={row.key} onChange={(e) => updateProperty(index, { key: e.target.value })} placeholder="Property name" />
                  <input value={row.value} onChange={(e) => updateProperty(index, { value: e.target.value })} placeholder="Value" />
                  <button type="button" className="icon-button" onClick={() => removeProperty(index)}><X size={15}/></button>
                </div>
              ))}
              {form.properties.length === 0 && <div className="inventory-property-empty">No custom properties added.</div>}
            </div>
            <div className="inventory-modal-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? "Saving..." : editing ? "Save Changes" : "Add Inventory"}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setShowForm(false)}>Cancel</button></div>
          </form>
        </div>
      )}

      {historyItem && (
        <div className="modal-backdrop">
          <div className="modal-card inventory-history-modal">
            <button type="button" className="modal-close" onClick={() => setHistoryItem(null)}><X size={18}/></button>
            <div><span className="eyebrow">ITEM HISTORY</span><h3>{historyItem.name}</h3><p>Every create, field update, removal and restore action for this inventory item.</p></div>
            <div className="inventory-history-list">
              {itemHistory.map((event) => (
                <div className="inventory-history-event" key={event.id}>
                  <div><span className={`inventory-audit-action ${event.action.toLowerCase()}`}>{event.action}</span><strong>{event.field_name ?? "record"}</strong></div>
                  <p><span>{formatValue(event.old_value)}</span><b>→</b><span>{formatValue(event.new_value)}</span></p>
                  <small>{new Date(event.changed_at).toLocaleString()} · {event.changed_by} · {event.source}</small>
                </div>
              ))}
              {itemHistory.length === 0 && <div className="inventory-empty">No history recorded for this item.</div>}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
