from __future__ import annotations
import json, os, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from .auth import require_devops
from .models import UserContext
from .user_store import list_users

router=APIRouter(prefix="/devops-tasks",tags=["devops-tasks"])
DATA=Path(os.getenv("DEVOPS_TASK_DATA_FILE","/data/devops-tasks.json")); LOCK=threading.RLock()
VALID_STATUSES={"backlog","inprogress","completed"}
NEXT_STATUS={"backlog":"inprogress","inprogress":"completed"}
def now(): return datetime.now(timezone.utc).isoformat()
def load():
 with LOCK:
  if not DATA.exists(): return []
  try: return json.loads(DATA.read_text())
  except (json.JSONDecodeError,OSError): return []
def save(rows):
 with LOCK:
  DATA.parent.mkdir(parents=True,exist_ok=True); tmp=DATA.with_suffix(".tmp"); tmp.write_text(json.dumps(rows,indent=2)); tmp.replace(DATA)
def get_task(rows,tid):
 for t in rows:
  if t["id"]==tid:return t
 raise HTTPException(404,"Task not found")
class Create(BaseModel):
 title:str=Field(min_length=3,max_length=200); description:str=Field(min_length=3,max_length=5000); assignee:str
class Update(BaseModel):
 title:str|None=Field(None,min_length=3,max_length=200); description:str|None=Field(None,min_length=3,max_length=5000); status:str|None=None
class Reassign(BaseModel): assignee:str
class Comment(BaseModel): text:str=Field(min_length=1,max_length=3000)
@router.get("/assignees")
def assignees(user:UserContext=Depends(require_devops)):
 return [{"email":u.email,"is_admin":u.is_admin} for u in list_users() if u.role=="devops" and u.is_active]
@router.get("")
def tasks(status:str|None=None,assignee:str|None=None,q:str|None=None,start_date:str|None=None,end_date:str|None=None,month:str|None=Query(None,description="YYYY-MM"),user:UserContext=Depends(require_devops)):
 rows=load()
 if not any([start_date,end_date,month]): month=datetime.now().strftime("%Y-%m")
 def keep(t):
  created=t["created_at"][:10]
  return (not status or t["status"]==status) and (not assignee or t["assignee"].lower()==assignee.lower()) and (not q or q.lower() in t["title"].lower() or q.lower() in t["description"].lower()) and (not month or created.startswith(month)) and (not start_date or created>=start_date) and (not end_date or created<=end_date)
 return sorted([t for t in rows if keep(t)],key=lambda x:x["updated_at"],reverse=True)
@router.post("",status_code=201)
def create(p:Create,user:UserContext=Depends(require_devops)):
 valid_assignees={u.email.lower() for u in list_users() if u.role=="devops" and u.is_active}
 if p.assignee.lower() not in valid_assignees: raise HTTPException(400,"Assignee must be an active DevOps portal user")
 rows=load(); ts=now(); t={"id":f"DT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}","title":p.title.strip(),"description":p.description.strip(),"assignee":p.assignee.lower(),"status":"backlog","created_by":user.username,"created_at":ts,"updated_at":ts,"comments":[],"history":[{"at":ts,"actor":user.username,"action":"Task created"}]}; rows.append(t);save(rows);return t
@router.put("/{tid}")
def update(tid:str,p:Update,user:UserContext=Depends(require_devops)):
 rows=load();t=get_task(rows,tid)
 if not user.is_admin and t["assignee"].lower()!=user.username.lower(): raise HTTPException(403,"Only the assignee or admin can edit this task")
 if p.status:
  if p.status not in VALID_STATUSES: raise HTTPException(400,"Invalid status")
  if p.status!=t["status"] and NEXT_STATUS.get(t["status"])!=p.status: raise HTTPException(409,"Tasks can only move Backlog → In Progress → Completed")
 old_status=t["status"]
 for k,v in p.model_dump(exclude_none=True).items(): t[k]=v.strip() if isinstance(v,str) else v
 t["updated_at"]=now();action=f"Status changed from {old_status} to {t['status']}" if p.status and p.status!=old_status else "Task updated";t["history"].append({"at":t["updated_at"],"actor":user.username,"action":action});save(rows);return t
@router.post("/{tid}/reassign")
def reassign(tid:str,p:Reassign,user:UserContext=Depends(require_devops)):
 if not user.is_admin: raise HTTPException(403,"Only DevOps admin can reassign tasks")
 valid_assignees={u.email.lower() for u in list_users() if u.role=="devops" and u.is_active}
 if p.assignee.lower() not in valid_assignees: raise HTTPException(400,"Assignee must be an active DevOps portal user")
 rows=load();t=get_task(rows,tid);old=t["assignee"];t["assignee"]=p.assignee.lower();t["updated_at"]=now();t["history"].append({"at":t["updated_at"],"actor":user.username,"action":f"Reassigned from {old} to {t['assignee']}"});save(rows);return t
@router.post("/{tid}/comments")
def comment(tid:str,p:Comment,user:UserContext=Depends(require_devops)):
 rows=load();t=get_task(rows,tid)
 if not user.is_admin and t["assignee"].lower()!=user.username.lower(): raise HTTPException(403,"Only the assignee or admin can comment")
 c={"id":uuid.uuid4().hex,"author":user.username,"text":p.text.strip(),"created_at":now()};t["comments"].append(c);t["updated_at"]=c["created_at"];save(rows);return t
