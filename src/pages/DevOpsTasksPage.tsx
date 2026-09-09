import { DragEvent, FormEvent, useEffect, useState } from "react";
import {
  commentDevOpsTask,
  createDevOpsTask,
  getDevOpsTaskAssignees,
  getDevOpsTasks,
  reassignDevOpsTask,
  updateDevOpsTask,
} from "../services/api";
import type { DevOpsTask, DevOpsTaskPriority, DevOpsTaskStatus } from "../types";

const statusLabel: Record<DevOpsTaskStatus, string> = { backlog: "Backlog", inprogress: "In Progress", completed: "Completed" };
const priorityLabel: Record<DevOpsTaskPriority, string> = { low: "Low", medium: "Medium", high: "High", critical: "Critical" };
const nextStatus: Partial<Record<DevOpsTaskStatus, DevOpsTaskStatus>> = { backlog: "inprogress", inprogress: "completed" };
type AssigneeOption = { email: string; is_admin: boolean };

export default function DevOpsTasksPage({ token, username, isAdmin }: { token: string; username: string; isAdmin: boolean }) {
  const current = new Date().toISOString().slice(0, 7);
  const [tasks, setTasks] = useState<DevOpsTask[]>([]);
  const [users, setUsers] = useState<AssigneeOption[]>([]);
  const [selected, setSelected] = useState<DevOpsTask | null>(null);
  const [error, setError] = useState("");
  const [month, setMonth] = useState(current);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [assignee, setAssignee] = useState("");
  const [search, setSearch] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [newAssignee, setNewAssignee] = useState(username);
  const [newPriority, setNewPriority] = useState<DevOpsTaskPriority>("medium");
  const [comment, setComment] = useState("");
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null);
  const [dragTarget, setDragTarget] = useState<DevOpsTaskStatus | null>(null);

  const loadTasks = async () => setTasks(await getDevOpsTasks(token, { month: start || end ? "" : month, status, priority, assignee, q: search, start_date: start, end_date: end }));
  const loadAssignees = async () => {
    const items = await getDevOpsTaskAssignees(token); setUsers(items);
    if (!items.some((item) => item.email === newAssignee)) {
      const own = items.find((item) => item.email.toLowerCase() === username.toLowerCase());
      setNewAssignee(own?.email ?? items[0]?.email ?? username);
    }
  };
  const load = async () => { try { setError(""); await Promise.all([loadTasks(), loadAssignees()]); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load tasks"); } };
  useEffect(() => { void load(); }, [token, month, status, priority, assignee, start, end]);

  async function create(event: FormEvent) {
    event.preventDefault();
    try { await createDevOpsTask({ title, description, assignee: newAssignee, priority: newPriority }, token); setTitle(""); setDescription(""); setNewPriority("medium"); await loadTasks(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to create task"); }
  }
  async function update(task: DevOpsTask, payload: { status?: DevOpsTaskStatus; title?: string; description?: string; priority?: DevOpsTaskPriority }) {
    try { const updated = await updateDevOpsTask(task.id, payload, token); if (selected?.id === task.id) setSelected(updated); await loadTasks(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to update task"); }
  }
  async function addComment() {
    if (!selected || !comment.trim()) return;
    try { const updated = await commentDevOpsTask(selected.id, comment, token); setSelected(updated); setComment(""); await loadTasks(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to add comment"); }
  }
  const canEdit = (task: DevOpsTask) => isAdmin || task.assignee.toLowerCase() === username.toLowerCase();
  function handleDragStart(event: DragEvent<HTMLButtonElement>, task: DevOpsTask) { if (!canEdit(task) || !nextStatus[task.status]) { event.preventDefault(); return; } setDraggedTaskId(task.id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", task.id); }
  function handleDragOver(event: DragEvent<HTMLDivElement>, targetStatus: DevOpsTaskStatus) { if (!draggedTaskId) return; const task = tasks.find((item) => item.id === draggedTaskId); if (!task || nextStatus[task.status] !== targetStatus) return; event.preventDefault(); event.dataTransfer.dropEffect = "move"; setDragTarget(targetStatus); }
  async function handleDrop(event: DragEvent<HTMLDivElement>, targetStatus: DevOpsTaskStatus) { event.preventDefault(); const taskId = event.dataTransfer.getData("text/plain") || draggedTaskId; const task = tasks.find((item) => item.id === taskId); setDraggedTaskId(null); setDragTarget(null); if (!task || nextStatus[task.status] !== targetStatus) return; await update(task, { status: targetStatus }); }

  return <section>
    <div className="section-heading"><div><span className="eyebrow">DEVOPS WORK MANAGEMENT</span><h2>DevOps Tasks</h2><p>Drag assigned tasks through the workflow and track priority from Low to Critical.</p></div></div>
    {error && <div className="form-error">{error}</div>}
    <form className="form-card two-column" onSubmit={create}>
      <label>Task title<input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task title" /></label>
      <label>Assignee<select value={newAssignee} onChange={(e) => setNewAssignee(e.target.value)}>{users.map((user) => <option key={user.email} value={user.email}>{user.email}{user.is_admin ? " (Admin)" : ""}</option>)}</select></label>
      <label>Priority<select value={newPriority} onChange={(e) => setNewPriority(e.target.value as DevOpsTaskPriority)}>{Object.entries(priorityLabel).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
      <label className="full-width">Description<textarea required rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <div className="full-width"><button className="primary-button">Create Task</button></div>
    </form>

    <div className="form-card" style={{ marginTop: 20 }}><div className="filter-grid">
      <label>Month<input type="month" value={month} onChange={(e) => { setMonth(e.target.value); setStart(""); setEnd(""); }} /></label>
      <label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option><option value="backlog">Backlog</option><option value="inprogress">In Progress</option><option value="completed">Completed</option></select></label>
      <label>Priority<select value={priority} onChange={(e) => setPriority(e.target.value)}><option value="">All priorities</option>{Object.entries(priorityLabel).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
      <label>Assignee<select value={assignee} onChange={(e) => setAssignee(e.target.value)}><option value="">All DevOps users</option>{users.map((user) => <option key={user.email} value={user.email}>{user.email}{user.is_admin ? " (Admin)" : ""}</option>)}</select></label>
      <label>Search title / details<input value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void loadTasks(); } }} /></label>
      <label>From<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
      <label>To<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      <button className="secondary-button" type="button" onClick={() => void loadTasks()}>Search</button>
    </div></div>

    <div className="task-board">{(["backlog", "inprogress", "completed"] as DevOpsTaskStatus[]).map((taskStatus) => <div className={`task-column ${dragTarget === taskStatus ? "drag-target" : ""}`} key={taskStatus} onDragOver={(e) => handleDragOver(e, taskStatus)} onDragLeave={() => setDragTarget((currentTarget) => currentTarget === taskStatus ? null : currentTarget)} onDrop={(e) => void handleDrop(e, taskStatus)}>
      <h3>{statusLabel[taskStatus]} <span>{tasks.filter((task) => task.status === taskStatus).length}</span></h3>
      {tasks.filter((task) => task.status === taskStatus).map((task) => { const draggable = canEdit(task) && Boolean(nextStatus[task.status]); return <button className={`task-card ${draggable ? "draggable" : ""}`} key={task.id} draggable={draggable} onDragStart={(e) => handleDragStart(e, task)} onDragEnd={() => { setDraggedTaskId(null); setDragTarget(null); }} onClick={() => setSelected(task)}>
        <div className="task-card-top"><small>{task.id}</small><span className={`priority-badge priority-${task.priority || "medium"}`}>{priorityLabel[task.priority || "medium"]}</span></div>
        <strong>{task.title}</strong><p>{task.description}</p><span>{task.assignee}</span><time>{new Date(task.updated_at).toLocaleString()}</time>{draggable && <em className="drag-hint">Drag to {statusLabel[nextStatus[task.status]!]}</em>}
      </button>; })}
    </div>)}</div>

    {selected && <div className="modal-backdrop"><div className="modal-card">
      <button className="modal-close" onClick={() => setSelected(null)}>×</button><span className="eyebrow">{selected.id}</span>
      <input className="task-title-input" defaultValue={selected.title} disabled={!canEdit(selected)} onBlur={(e) => e.target.value !== selected.title && update(selected, { title: e.target.value })} />
      <textarea rows={5} defaultValue={selected.description} disabled={!canEdit(selected)} onBlur={(e) => e.target.value !== selected.description && update(selected, { description: e.target.value })} />
      <div className="filter-grid">
        <label>Status<select disabled={!canEdit(selected) || selected.status === "completed"} value={selected.status} onChange={(e) => update(selected, { status: e.target.value as DevOpsTaskStatus })}><option value={selected.status}>{statusLabel[selected.status]}</option>{nextStatus[selected.status] && <option value={nextStatus[selected.status]}>{statusLabel[nextStatus[selected.status]!]}</option>}</select></label>
        <label>Priority<select disabled={!canEdit(selected)} value={selected.priority || "medium"} onChange={(e) => update(selected, { priority: e.target.value as DevOpsTaskPriority })}>{Object.entries(priorityLabel).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
        {isAdmin && <label>Reassign<select value={selected.assignee} onChange={async (e) => { const updated = await reassignDevOpsTask(selected.id, e.target.value, token); setSelected(updated); await loadTasks(); }}>{users.map((user) => <option key={user.email} value={user.email}>{user.email}{user.is_admin ? " (Admin)" : ""}</option>)}</select></label>}
      </div>
      <h3>Comments</h3><div className="comments">{selected.comments.map((item) => <div key={item.id}><strong>{item.author}</strong><small>{new Date(item.created_at).toLocaleString()}</small><p>{item.text}</p></div>)}</div>
      {canEdit(selected) && <div className="comment-box"><textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add a comment..." /><button className="primary-button" onClick={addComment}>Add Comment</button></div>}
      <h3>History</h3>{selected.history.slice().reverse().map((item, index) => <p key={index} className="history-line"><strong>{item.actor}</strong> · {item.action} · {new Date(item.at).toLocaleString()}</p>)}
    </div></div>}
  </section>;
}
