#!/usr/bin/env python3
"""Post the next ready item from content/manifest.json to the Facebook Page.

Reads content/state.json for the queue index, posts one item via the
Facebook Graph API, then advances the index. Exits 0 without posting when
the queue is empty or the next item is not ready yet.

Videos are posted as REELS via the video_reels 3-step upload flow.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

PAGE_ID = os.environ["PAGE_ID"]
TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
GRAPH = "https://graph.facebook.com/v21.0"


def api_post_text(message):
    data = urllib.parse.urlencode(
        {"message": message, "access_token": TOKEN}
    ).encode()
    req = urllib.request.Request(f"{GRAPH}/{PAGE_ID}/feed", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post_media(edge, filepath, text_field, text):
    cmd = [
        "curl", "-sS", "-X", "POST", f"{GRAPH}/{PAGE_ID}/{edge}",
        "-F", f"source=@{filepath}",
        "-F", f"{text_field}={text}",
        "-F", f"access_token={TOKEN}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        print("curl failed:", proc.stderr.strip())
        sys.exit(1)
    return json.loads(proc.stdout)


def _graph_post(path, params):
    params = dict(params)
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{GRAPH}{path}", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _graph_get(path, params):
    params = dict(params)
    params["access_token"] = TOKEN
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{GRAPH}{path}?{qs}", method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post_reel(filepath, description):
    """Publish a video file as a Facebook Page Reel."""
    if not TOKEN:
        print("FB_PAGE_TOKEN is missing.")
        sys.exit(1)
    if not os.path.isfile(filepath):
        print(f"Video file not found: {filepath}")
        sys.exit(1)

    # Step 1: initialize upload session
    init = _graph_post(f"/{PAGE_ID}/video_reels", {"upload_phase": "start"})
    if "error" in init:
        print("Reels init error:", json.dumps(init["error"], indent=2))
        sys.exit(1)
    video_id = init.get("video_id")
    upload_url = init.get("upload_url")
    if not video_id or not upload_url:
        print("Reels init returned no video_id/upload_url:", json.dumps(init))
        sys.exit(1)
    print(f"Reels upload session started: video_id={video_id}")

    # Step 2: upload bytes to rupload.facebook.com
    file_size = os.path.getsize(filepath)
    cmd = [
        "curl", "-sS", "-X", "POST", upload_url,
        "-H", f"Authorization: OAuth {TOKEN}",
        "-H", "Content-Type: application/octet-stream",
        "-H", "offset: 0",
        "-H", f"file_size: {file_size}",
        "--data-binary", f"@{filepath}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        print("Reels byte upload failed:", proc.stderr.strip())
        sys.exit(1)
    try:
        up = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("Reels upload returned non-JSON:", proc.stdout[:300])
        sys.exit(1)
    if "error" in up or not up.get("success"):
        print("Reels upload not acknowledged:", json.dumps(up, indent=2))
        sys.exit(1)
    print("Reels bytes uploaded.")

    # Step 2b: confirm upload complete (best-effort)
    for attempt in range(6):
        try:
            st = _graph_get(f"/{video_id}", {"fields": "status"})
            uph = st.get("status", {}).get("uploading_phase", {}).get("status")
            if uph == "complete":
                break
        except Exception as e:
            print(f"Status poll failed (continuing): {e}")
            break
        time.sleep(10)

    # Step 3: finish AND publish (video_state=PUBLISHED is critical!)
    result = _graph_post(
        f"/{PAGE_ID}/video_reels",
        {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": description,
        },
    )
    if "error" in result:
        print("Reels publish error:", json.dumps(result["error"], indent=2))
        sys.exit(1)
    if not result.get("success"):
        print("Reels publish not confirmed:", json.dumps(result, indent=2))
        sys.exit(1)

    print(f"Reel PUBLISHED: video_id={video_id}")
    return result


def main():
    if not TOKEN:
        print("FB_PAGE_TOKEN secret is missing.")
        print("Add it in the repo: Settings > Secrets and variables > Actions > New repository secret.")
        sys.exit(1)

    with open("content/manifest.json") as fh:
        items = json.load(fh)["items"]
    with open("content/state.json") as fh:
        state = json.load(fh)

    if not items:
        print("Queue is empty. Nothing to post.")
        return

    idx = state.get("index", 0) % len(items)
    item = items[idx]

    if not item.get("ready"):
        print(f"Item {idx} ({item['type']}) is not ready yet. Skipping this slot.")
        return

    caption = item.get("caption", "")
    kind = item["type"]
    if kind == "text":
        result = api_post_text(caption)
    elif kind == "image":
        result = api_post_media("photos", item["file"], "caption", caption)
    elif kind == "video":
        result = api_post_reel(item["file"], caption)
    else:
        print(f"Unknown item type: {kind}")
        sys.exit(1)

    if "error" in result:
        print("Facebook API error:", json.dumps(result["error"], indent=2))
        sys.exit(1)

    print("Posted OK:", result.get("id", result.get("success")))
    state["index"] = (idx + 1) % len(items)
    with open("content/state.json", "w") as fh:
        json.dump(state, fh, indent=2)


if __name__ == "__main__":
    main()
