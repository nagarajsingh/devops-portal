import { FormEvent, useEffect, useState } from "react";
import {
  commentDevOpsTask,
  createDevOpsTask,
  getDevOpsTasks,
  getPortalUsers,
  reassignDevOpsTask,
  updateDevOpsTask,
} from "../services/api";
import type { DevOpsTask, DevOpsTaskStatus, PortalUser } from "../types";

const statusLabel: Record<DevOpsTaskStatus, string> = {
  backlog: "Backlog",
  inprogress: "In Progress",
  completed: "Completed",
};

export default function DevOpsTasksPage({
  token,
  username,
  isAdmin,
}: {
  token: string;
  username: string;
  isAdmin: boolean;
}) {
  const current = new Date().toISOString().slice(0, 7);
  const [tasks, setTasks] = useState<DevOpsTask[]>([]);
  const [users, setUsers] = useState<PortalUser[]>([]);
  const [selected, setSelected] = useState<DevOpsTask | null>(null);
  const [error, setError] = useState("");
  const [month, setMonth] = useState(current);
  const [status, setStatus] = useState("");
  const [assignee, setAssignee] = useState("");
  const [search, setSearch] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [newAssignee, setNewAssignee] = useState(username);
  const [comment, setComment] = useState("");

  const load = async () => {
    try {
      setError("");
      setTasks(
        await getDevOpsTasks(token, {
          month: start || end ? "" : month,
          status,
          assignee,
          q: search,
          start_date: start,
          end_date: end,
        }),
      );
      if (isAdmin) {
        setUsers((await getPortalUsers(token)).filter((user) => user.role === "devops" && user.is_active));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load tasks");
    }
  };

  useEffect(() => {
    void load();
  }, [token, month, status, assignee, start, end]);

  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      await createDevOpsTask({ title, description, assignee: newAssignee }, token);
      setTitle("");
      setDescription("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create task");
    }
  }

  async function update(task: DevOpsTask, payload: { status?: DevOpsTaskStatus; title?: string; description?: string }) {
    try {
      const updated = await updateDevOpsTask(task.id, payload, token);
      setSelected(updated);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update task");
    }
  }

  async function addComment() {
    if (!selected || !comment.trim()) return;
    try {
      const updated = await commentDevOpsTask(selected.id, comment, token);
      setSelected(updated);
      setComment("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add comment");
    }
  }

  const canEdit = (task: DevOpsTask) => isAdmin || task.assignee.toLowerCase() === username.toLowerCase();

  return (
    <section>
      <div className="section-heading">
        <div>
          <span className="eyebrow">DEVOPS WORK MANAGEMENT</span>
          <h2>DevOps Tasks</h2>
          <p>Monthly backlog, active work and completed tasks with assignment history and comments.</p>
        </div>
      </div>

      {error && <div className="form-error">{error}</div>}

      <form className="form-card two-column" onSubmit={create}>
        <label>
          Task title
          <input required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Task title" />
        </label>
        <label>
          Assignee
          {isAdmin ? (
            <select value={newAssignee} onChange={(event) => setNewAssignee(event.target.value)}>
              {users.map((user) => (
                <option key={user.id} value={user.email}>{user.email}</option>
              ))}
            </select>
          ) : (
            <input value={username} readOnly />
          )}
        </label>
        <label className="full-width">
          Description
          <textarea required rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>
        <div className="full-width">
          <button className="primary-button">Create Task</button>
        </div>
      </form>

      <div className="form-card" style={{ marginTop: 20 }}>
        <div className="filter-grid">
          <label>
            Month
            <input
              type="month"
              value={month}
              onChange={(event) => {
                setMonth(event.target.value);
                setStart("");
                setEnd("");
              }}
            />
          </label>
          <label>
            Status
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All</option>
              <option value="backlog">Backlog</option>
              <option value="inprogress">In Progress</option>
              <option value="completed">Completed</option>
            </select>
          </label>
          <label>
            Assignee
            <input value={assignee} onChange={(event) => setAssignee(event.target.value)} placeholder="user@mashreq.com" />
          </label>
          <label>
            Search title / details
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void load();
                }
              }}
            />
          </label>
          <label>
            From
            <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
          </label>
          <label>
            To
            <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
          </label>
          <button className="secondary-button" type="button" onClick={() => void load()}>Search</button>
        </div>
      </div>

      <div className="task-board">
        {(["backlog", "inprogress", "completed"] as DevOpsTaskStatus[]).map((taskStatus) => (
          <div className="task-column" key={taskStatus}>
            <h3>{statusLabel[taskStatus]} <span>{tasks.filter((task) => task.status === taskStatus).length}</span></h3>
            {tasks.filter((task) => task.status === taskStatus).map((task) => (
              <button className="task-card" key={task.id} onClick={() => setSelected(task)}>
                <small>{task.id}</small>
                <strong>{task.title}</strong>
                <p>{task.description}</p>
                <span>{task.assignee}</span>
                <time>{new Date(task.updated_at).toLocaleString()}</time>
              </button>
            ))}
          </div>
        ))}
      </div>

      {selected && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <button className="modal-close" onClick={() => setSelected(null)}>×</button>
            <span className="eyebrow">{selected.id}</span>
            <input
              className="task-title-input"
              defaultValue={selected.title}
              disabled={!canEdit(selected)}
              onBlur={(event) => event.target.value !== selected.title && update(selected, { title: event.target.value })}
            />
            <textarea
              rows={5}
              defaultValue={selected.description}
              disabled={!canEdit(selected)}
              onBlur={(event) => event.target.value !== selected.description && update(selected, { description: event.target.value })}
            />
            <div className="filter-grid">
              <label>
                Status
                <select
                  disabled={!canEdit(selected)}
                  value={selected.status}
                  onChange={(event) => update(selected, { status: event.target.value as DevOpsTaskStatus })}
                >
                  {Object.entries(statusLabel).map(([key, value]) => (
                    <option key={key} value={key}>{value}</option>
                  ))}
                </select>
              </label>
              {isAdmin && (
                <label>
                  Reassign
                  <select
                    value={selected.assignee}
                    onChange={async (event) => {
                      const updated = await reassignDevOpsTask(selected.id, event.target.value, token);
                      setSelected(updated);
                      await load();
                    }}
                  >
                    {users.map((user) => (
                      <option key={user.id} value={user.email}>{user.email}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
            <h3>Comments</h3>
            <div className="comments">
              {selected.comments.map((item) => (
                <div key={item.id}>
                  <strong>{item.author}</strong>
                  <small>{new Date(item.created_at).toLocaleString()}</small>
                  <p>{item.text}</p>
                </div>
              ))}
            </div>
            {canEdit(selected) && (
              <div className="comment-box">
                <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Add a comment..." />
                <button className="primary-button" onClick={addComment}>Add Comment</button>
              </div>
            )}
            <h3>History</h3>
            {selected.history.slice().reverse().map((item, index) => (
              <p key={index} className="history-line">
                <strong>{item.actor}</strong> · {item.action} · {new Date(item.at).toLocaleString()}
              </p>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
