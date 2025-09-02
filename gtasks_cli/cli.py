# Quickstart.py from google docs
import os.path
import argparse

from pathlib import Path
from google.auth import default
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/tasks"]

SORT_ASCENDING = 0
SORT_DESCENDING = 1
SORT_TITLE = 0
SORT_DUE_DATE = 1

def printTask(task):
    print((f"{task['id']}|"
           f"{task['title']}|"
           f"{task.get('notes', '')}|"
           f"{'' if task['status'] == 'needsAction' else ' '}|"
           f"{task.get('due', '')}|"
           f"{task.get('position', '')}"))

def printTaskList(tasklist):
    print((f"{tasklist['id']}|"
           f"{tasklist['title']}"))

# Class to create dates and handle RFC3339 format
# Input dates to the program must all be of the form dd/mm/yyyy
# Currently the google api doesn't provide a way to manipulate 
# and view time stamps, so the RFC string time would be set to 
# yyyy-mm-ddT00:00:00.000Z
class RFCDate:
    def __init__(self, date: str):
        datelist: list[str] = date.split('/')
        if (len(datelist) != 3):
            raise Exception("Incorrect date format: use dd/mm/yyyy")
        day: int = int(datelist[0])
        month: int = int(datelist[1])
        year: int = int(datelist[2])
        if (year < 0):
            raise Exception("Year must be a posiitve integer")
        if (month < 1 or month > 12):
            raise Exception("Month must be an integer between 0 and 12")
        if (not self.verifyDate(month, day, year)):
            raise Exception("Invalid date for given month and year")
        self.day = day
        self.month = month
        self.year = year
    def verifyDate(self, month, day, year):
        isLeap: bool = (year % 400 == 0) or ((year % 100 != 0) and (year % 4 == 0))
        if (day <= 0):
            return False
        match month:
            case 1 | 3 | 5 | 7 | 8 | 10 | 12:
                return day <= 31
            case 4 | 6 | 9 | 11:
                return day <= 30
            case 2:
                return (day <= 29) if isLeap else (day <= 28)
    def toRFC(self):
        return f"{self.year:04}-{self.month:02}-{self.day:02}T00:00:00.000Z"


class Task:
    def __init__(self, title: str, notes: str, due: str) -> None:
        self.kind = "tasks#task"
        if (title == ""):
            raise Exception("Cannot create task with empty title")
        self.title = title
        self.date = RFCDate(due)
        self.notes = notes if notes != "" else None
    def to_json(self):
        notesFieldStr: str = "" if self.date is None else f'"notes": "{self.notes}",'
        dateFieldStr: str = "" if self.date is None else f'"due": "{self.date.toRFC()}",'
        # return f'{"kind": "{self.kind}","title": "{self.title}",{notesFieldStr}{dateFieldStr}}'
        return {
            "title": self.title,
            "notes": self.notes,
            "due": self.date.toRFC()
        }

def clearList(service, tasklist: str):
    """
    Clears all completed tasks from the specified task list. 
    The affected tasks will be marked as 'hidden' and no longer be returned by 
    default when retrieving all tasks for a task list
    """
    result = service.tasks().clear(tasklist=tasklist).execute()
    if (len(result) != 0):
        raise Exception(f"Failed to clear list {tasklist}:", result)
    
def deleteTask(service, tasklist: str, task: str):
    """
    Deletes the specified task from the task list. If the task is assigned, 
    both the assigned task and the original task (in Docs, Chat Spaces) are deleted. 
    To delete the assigned task only, navigate to the assignment surface and 
    unassign the task from there.
    """
    result = service.tasks().delete(tasklist=tasklist, task=task).execute()
    if (len(result) != 0):
        raise Exception(f"Failed to delete task {task} from list {tasklist}:", result)

def getTask(service, tasklist: str, task: str):
    """
    Returns the specified task
    """
    result = service.tasks().get(tasklist=tasklist, task=task).execute()
    printTask(result)
    return result

def insertTask(service, tasklist: str, task, parent: str, previous: str):
    """
    Creates a new task on the specified task list. Tasks assigned from Docs
    or Chat Spaces cannot be inserted from Tasks Public API; they can only 
    be created by assigning them from Docs or Chat Spaces. A user can have 
    up to 20,000 non-hidden tasks per list and up to 100,000 tasks in total at a time

    parent: parent task id, for top level omit
    previous: previous sibling task id, for first position omit
    """
    args = {
        "tasklist": tasklist,
        "parent": parent,
        "previous": previous,
        "body": task.to_json()
    }

    result = service.tasks().insert(**args).execute()
    printTask(result)

def listTasks(service, 
              tasklist: str, 
              showCompleted: bool, 
              dueMin: str, 
              dueMax: str, 
              sort_category: int, 
              sort_direction: int):
    """
    Returns all tasks in the specified task list. Doesn't return assigned tasks 
    by default (from Docs, Chat Spaces). A user can have up to 20,000 non-hidden 
    tasks per list and up to 100,000 tasks in total at a time.
    """
    args = {
        "tasklist": tasklist,
        "dueMax": dueMax,
        "dueMin": dueMin,
        "maxResults": 100,
        "showCompleted": showCompleted,
        "showHidden": showCompleted
    }

    args = {k: v for k, v in args.items() if (type(v) != str) or v != ""}
    result = service.tasks().list(**args).execute()
    items = result.get("items", [])

    if (sort_category == SORT_DUE_DATE):
        items.sort(key=lambda t: t.get('due', ''), reverse=(sort_direction==SORT_DESCENDING))

    if (sort_category == SORT_TITLE):
        items.sort(key=lambda t: t.get('title', ''), reverse=(sort_direction==SORT_DESCENDING))

    if not items:
        return

    for item in items:
        printTask(item)

def moveTask(service, tasklist: str, task: str, parent: str, previous: str, destinationTaskList: str):
    """
    Moves the specified task to another position in the destination task list. 
    If the destination list is not specified, the task is moved within its current 
    list. This can include putting it as a child task under a new parent and/or 
    move it to a different position among its sibling tasks. A user can have up 
    to 2,000 subtasks per task.
    """
    args = {
        "tasklist": tasklist,
        "task": task,
        "parent": parent,
        "previous": previous,
        "destinationTaskList": destinationTaskList,
    }

    args = {k: v for k, v in args.items() if (type(v) != str) or v != ""}
    result = service.tasks().move(**args).execute()
    printTask(result)

def updateTask(service, tasklist: str, task: str, field: str, newValue):
    """
    Updates the specified field in the task, doesn't wipe other fields
    """

    if (field == "due"):
        newValue = RFCDate(newValue).toRFC()

    args = {
        "tasklist": tasklist,
        "task": task,
        "body": {
            field: newValue
        }
    }

    args = {k: v for k, v in args.items() if (type(v) != str) or v != ""}
    result = service.tasks().patch(**args).execute()
    printTask(result)

def toggleCompleted(service, tasklist: str, taskID: str):
    """
    Toggle complete status of a task
    """
    task = getTask(service, tasklist, taskID)
    completed = True if task.get("status", "") == "completed" else False
    updateTask(service, tasklist, taskID, "status", "needsAction" if completed else "completed")


def deleteTaskList(service, tasklist: str):
    """
    Deletes the authenticated user's specified task list. If the list 
    contains assigned tasks, both the assigned tasks and the original 
    tasks in the assignment surface (Docs, Chat Spaces) are deleted.
    """
    result = service.tasklists().delete(tasklist=tasklist).execute()
    if (result != ""):
        raise Exception(f"Couldn't delete task list {tasklist}: {result}")

def getTaskList(service, tasklist: str):
    """
    Returns the authenticated user's specified task list.
    """
    result = service.tasklists().get(tasklist=tasklist).execute()
    printTaskList(result)

def createTaskList(service, title: str):
    """
    Creates a new task list and adds it to the authenticated user's 
    task lists. A user can have up to 2000 lists at a time.
    """
    result = service.tasklists().insert(body={"title": title}).execute()
    printTaskList(result)

def listTaskLists(service, sort_direction):
    """
    Returns all the authenticated user's task lists. A user can have 
    up to 2000 lists at a time.
    """
    result = service.tasklists().list().execute()
    items = result.get("items", [])

    items.sort(key=lambda t: t.get('title', ''), reverse=(sort_direction==SORT_DESCENDING))

    if not items:
        return

    for item in items:
        printTaskList(item)

def updateTaskList(service, newTitle: str):
    """
    Updates the authenticated user's specified task list.
    """
    result = service.tasklists().update(body={"title": newTitle}).execute()
    printTaskList(result)

def main():
    parser = argparse.ArgumentParser(
        description="Google tasks cli interface"
    )
    parser.add_argument("action", 
                        choices=["clearList", 
                                 "delete", "get", "insert", "list", "move", "update", "toggleCompleted",
                                 "deleteList", "getList", "create", "listList", "updateList" ],
                        help="The action to perform (must be one of: delete, get, insert, list, move, update, toggleCompleted, deleteList, getList, create, listList, updateList)")
    parser.add_argument("--tasklist", "-l", 
                        type=str, default="@default", 
                        help="Tasklist id to act on (default: @default)")
    parser.add_argument("--task", "-t", 
                        type=str, default="", 
                        help="Task id to act on")
    parser.add_argument("--parent", "-a",
                        type=str, default="",
                        help="ID of the new parent of the task")
    parser.add_argument("--previous", "-p",
                        type=str, default="",
                        help="ID of the previous sibling of the task")
    parser.add_argument("--title", "-g",
                        type=str, default="",
                        help="New title of the task/tasklist")
    parser.add_argument("--notes", "-n",
                        type=str, default="",
                        help="Description of the task")
    parser.add_argument("--due", "-d",
                        type=str, default="",
                        help="Due date of the new task, pass in dd/mm/yyyy format")
    parser.add_argument("--showCompleted", "-c",
                        action="store_true", default=False,
                        help="Whether to show completed and hidden tasks")
    parser.add_argument("--dueMin", "-b",
                        type=str, default="",
                        help="Start date to filter tasks on(dd/mm/yyyy)")
    parser.add_argument("--dueMax", "-e",
                        type=str, default="",
                        help="End date to filter tasks on(dd/mm/yyyy)")
    sort_category = parser.add_mutually_exclusive_group()
    sort_category.add_argument("--sortTitle", dest="sort_category", action="store_const", 
                               const=SORT_TITLE, help="Sort on title")
    sort_category.add_argument("--sortDue", dest="sort_category", action="store_const", 
                               const=SORT_DUE_DATE, help="Sort on due date")
    sort_direction = parser.add_mutually_exclusive_group()
    sort_direction.add_argument("--asc", dest="sort_direction", action="store_const",
                                const=SORT_ASCENDING, help="Sort in ascending manner")
    sort_direction.add_argument("--desc", dest="sort_direction", action="store_const",
                                const=SORT_DESCENDING, help="Sort in descending manner")
    parser.add_argument("--destinationTaskList", "-m",
                        type=str, default="",
                        help="Tasklist to move the task to")
    parser.add_argument("--field", "-f",
                        type=str, default="",
                        help="Field of the task to update")
    parser.add_argument("--value", "-v",
                        type=str, default="",
                        help="Value of the updated field")


    args = parser.parse_args()
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    token_path: Path = Path.home() / ".local" / "share" / "gtasks" / "token.json"
    cred_path: Path = Path.home() / ".config" / "gtasks" / "credentials.json"
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            cred_path, SCOPES
        )
        creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    try:
        service = build("tasks", "v1", credentials=creds)

        match (args.action):
            case "clearList":
                clearList(service, args.tasklist)
            case "delete":
                deleteTask(service, args.tasklist, args.task)
            case "get":
                getTask(service, args.tasklist, args.task)
            case "insert":
                task = Task(args.title, args.notes, args.due)
                insertTask(service, args.tasklist, task, args.parent, args.previous)
            case "list":
                listTasks(service, args.tasklist, args.showCompleted, args.dueMin, args.dueMax, args.sort_category, args.sort_direction)
            case "move":
                moveTask(service, args.tasklist, args.task, args.parent, args.previous, args.destinationTaskList)
            case "update":
                updateTask(service, args.tasklist, args.task, args.field, args.value)
            case "toggleCompleted":
                toggleCompleted(service, args.tasklist, args.task)
            case "deleteList":
                deleteTaskList(service, args.tasklist)
            case "getList":
                getTaskList(service, args.tasklist)
            case "create":
                createTaskList(service, args.title)
            case "listList":
                listTaskLists(service, SORT_ASCENDING)
            case "updateList":
                updateTaskList(service, args.title)


    except HttpError as err:
        print(err)


# if __name__ == "__main__":
#     main()
