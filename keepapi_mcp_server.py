from fastmcp import FastMCP
import gkeepapi, json, os, hashlib

STATE_FILE = os.path.join(os.path.dirname(__file__), "keep_state.json")
mcp = FastMCP("keepapi")
keep = gkeepapi.Keep()

@mcp.tool()
def keep_login(email: str, app_password: str):
    """
    Login to Google Keep using an App Password.
    
    IMPORTANT: You MUST use an App Password, NOT your regular Google password.
    
    To create an App Password:
    1. Enable 2-Factor Authentication on your Google account:
       https://myaccount.google.com/signinoptions/two-step-verification
    2. Generate an App Password at:
       https://myaccount.google.com/apppasswords
    3. Select "Other (Custom name)" and name it "Keep MCP"
    4. Copy the 16-character password and paste it here.
    
    Args:
        email: Your Google account email
        app_password: The 16-character App Password (NOT your regular password)
    """
    global keep
    keep = gkeepapi.Keep()
    try:
        success = keep.login(email, app_password)
        if success:
            state = keep.dump()
            with open(STATE_FILE, "w") as f:
                json.dump({"email": email, "state": state}, f)
            return {
                "success": True,
                "message": "Login successful! Master token obtained.",
                "master_token": keep.getMasterToken(),
                "note": "You can now use keep_resume() to reconnect without re-authenticating."
            }
        else:
            return {
                "success": False,
                "message": "Login returned false. Check your credentials.",
                "master_token": None
            }
    except gkeepapi.exception.LoginException as e:
        error_msg = str(e)
        if "BadAuthentication" in error_msg:
            return {
                "success": False,
                "message": "BadAuthentication: Google rejected the credentials.",
                "detail": "You MUST use an App Password (16 chars), not your regular Google password.",
                "instructions": [
                    "1. Enable 2-Factor Auth: https://myaccount.google.com/signinoptions/two-step-verification",
                    "2. Generate App Password: https://myaccount.google.com/apppasswords",
                    "3. Select 'Other (Custom name)', name it 'Keep MCP'",
                    "4. Paste the 16-character password here"
                ],
                "master_token": None
            }
        return {"success": False, "message": f"Login failed: {error_msg}", "master_token": None}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}", "master_token": None}

@mcp.tool()
def keep_resume(email: str):
    """Resume a previous session using cached state."""
    global keep
    if not os.path.exists(STATE_FILE):
        return {"success": False, "message": "No cached state found. Use keep_login() first."}
    with open(STATE_FILE) as f:
        data = json.load(f)
    keep = gkeepapi.Keep()
    keep.restore(data["email"], data["state"])
    return {"success": True, "message": "Session resumed"}

@mcp.tool()
def keep_sync():
    """Sync with Google Keep server."""
    keep.sync()
    return {"success": True, "message": "Sync complete"}

@mcp.tool()
def keep_list_notes():
    """List all notes (titles + IDs)."""
    notes = []
    for note in keep.all():
        notes.append({
            "id": note.id,
            "title": note.title,
            "text": note.text,
            "color": note.color.name if note.color else None,
            "pinned": note.pinned,
            "archived": note.archived,
            "labels": [l.name for l in note.labels.all()],
            "timestamps": {
                "created": str(note.timestamps.created),
                "edited": str(note.timestamps.edited),
                "updated": str(note.timestamps.updated),
                "trashed": str(note.timestamps.trashed) if note.timestamps.trashed else None,
            }
        })
    return {"count": len(notes), "notes": notes}

@mcp.tool()
def keep_search_notes(query: str):
    """Search notes by query string."""
    results = keep.find(query=query)
    notes = []
    for note in results:
        notes.append({"id": note.id, "title": note.title, "text": note.text})
    return {"count": len(notes), "notes": notes}

@mcp.tool()
def keep_create_note(title: str, text: str, color: str = "WHITE"):
    """Create a new text note."""
    note = keep.createNote(title, text)
    if color:
        note.color = gkeepapi.node.ColorValue[color.upper()]
    keep.sync()
    return {"success": True, "id": note.id, "title": note.title}

@mcp.tool()
def keep_create_list(title: str, items: list):
    """Create a new list note. items = [[text, checked], ...]"""
    note = keep.createList(title, [(text, checked) for text, checked in items])
    keep.sync()
    return {"success": True, "id": note.id, "title": note.title}

@mcp.tool()
def keep_update_note(note_id: str, title: str = None, text: str = None):
    """Update a note's title and/or text."""
    note = keep.get(note_id)
    if note:
        if title: note.title = title
        if text: note.text = text
        keep.sync()
        return {"success": True, "message": "Note updated"}
    return {"success": False, "message": "Note not found"}

@mcp.tool()
def keep_delete_note(note_id: str):
    """Delete (trash) a note."""
    note = keep.get(note_id)
    if note:
        note.delete()
        keep.sync()
        return {"success": True, "message": "Note deleted"}
    return {"success": False, "message": "Note not found"}

@mcp.tool()
def keep_archive_note(note_id: str):
    """Archive a note."""
    note = keep.get(note_id)
    if note:
        note.archived = True
        keep.sync()
        return {"success": True, "message": "Note archived"}
    return {"success": False, "message": "Note not found"}

@mcp.tool()
def keep_list_labels():
    """List all labels."""
    labels = [{"id": l.id, "name": l.name} for l in keep.labels()]
    return {"count": len(labels), "labels": labels}

@mcp.tool()
def keep_add_label(note_id: str, label_name: str):
    """Add a label to a note (creates label if it doesn't exist)."""
    note = keep.get(note_id)
    if not note:
        return {"success": False, "message": "Note not found"}
    label = keep.findLabel(label_name)
    if not label:
        label = keep.createLabel(label_name)
    note.labels.add(label)
    keep.sync()
    return {"success": True, "message": f"Label '{label_name}' added"}

@mcp.tool()
def keep_get_state():
    """Get serialized state for debugging."""
    return {
        "state_file_exists": os.path.exists(STATE_FILE),
        "state_file_path": STATE_FILE,
        "state": keep.dump() if keep else None
    }

@mcp.tool()
def keep_export_to_vault(vault_dir: str = r"C:\dev\Desktop-Projects\Helpful-Docs-Prompts\VAULTS-OBSIDIAN\Notesandclippings\Notesandclippings\Untitled"):
    """Export all Keep notes to Obsidian vault as markdown files."""
    import re
    from pathlib import Path

    vault = Path(vault_dir)
    vault.mkdir(parents=True, exist_ok=True)

    def sanitize(name):
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = name.strip('. ')
        return name[:100] or "untitled"

    def to_markdown(note):
        labels = [l.name for l in note.labels.all()]
        fm = {
            "title": note.title,
            "source": "google_keep",
            "id": note.id,
            "color": note.color.name if note.color else None,
            "pinned": note.pinned,
            "archived": note.archived,
            "labels": labels,
        }
        md = "---\n"
        for k, v in fm.items():
            if isinstance(v, list):
                md += f"{k}:\n" + "".join(f"  - {i}\n" for i in v)
            elif isinstance(v, bool):
                md += f"{k}: {str(v).lower()}\n"
            else:
                md += f"{k}: {v}\n"
        md += "---\n\n"
        if note.title:
            md += f"# {note.title}\n\n"
        if note.type == gkeepapi.node.List:
            for item in note.items:
                cb = "[x]" if item.checked else "[ ]"
                md += f"- {cb} {item.text}\n"
        else:
            md += note.text + "\n"
        md += "\n---\n*Imported from Google Keep*\n"
        return md

    seen = set()
    saved = 0
    for note in keep.all():
        key = hashlib.sha256((note.title + note.text).encode()).hexdigest()[:16]
        if key in seen:
            continue
        seen.add(key)

        fname = sanitize(note.title or "untitled")
        path = vault / f"{fname}.md"
        ctr = 1
        while path.exists():
            path = vault / f"{fname}_{ctr}.md"
            ctr += 1

        path.write_text(to_markdown(note), encoding="utf-8")
        saved += 1

    return {"success": True, "saved": saved, "vault": str(vault)}

if __name__ == "__main__":
    mcp.run()
