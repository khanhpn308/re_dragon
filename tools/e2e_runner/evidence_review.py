#!/usr/bin/env python3
"""Fail-closed screenshot integrity gate and human visual review index.

Hashes, filenames and pixels alone are not semantic gameplay proof.
This tool NEVER emits ACCEPTED / VERIFIED / COMBAT_PASS.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path
import struct
import sys

PNG_SIG = b"\x89PNG\r\n\x1a\n"
REQUIRED = {
 "summon_result": "An actual new hero, not a summon animation",
 "owned_hero": "Owned account hero with matching server/database instance",
 "hero_picker": "Owned-hero selector after tapping right-hand formation +",
 "formation_saved": "Active formation slot occupied by owned hero",
 "formation_relogin": "Same formation after fresh login",
 "stage_selected": "Actual Phó bản / Chiến đấu stage selected",
 "battle_active": "Battle scene with hero and enemy, not Adventure or Connecting Server",
 "battle_result": "Win/loss result and rewards persisted",
}

def sha256(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for part in iter(lambda:f.read(1048576),b""):h.update(part)
 return h.hexdigest()

def check_png(path):
 with path.open("rb") as f: header=f.read(24)
 if len(header)<24 or not header.startswith(PNG_SIG) or header[12:16]!=b"IHDR":
  raise ValueError("not a valid PNG header")
 width,height=struct.unpack(">II",header[16:24])
 if width<=0 or height<=0 or width>16000 or height>16000:
  raise ValueError("invalid screenshot dimensions")
 return width,height

def verify(root, manifest):
 """Verify file identity, no path escape/reuse; never assess gameplay semantics."""
 root=Path(root).resolve()
 entries=manifest.get("artifacts")
 if not isinstance(entries,dict) or not entries:raise ValueError("empty screenshot ledger")
 report=[]
 seen=set()
 for key,item in entries.items():
  if not isinstance(item,dict) or not str(key).endswith(".png"):
   raise ValueError("non-PNG entry")
  raw=item.get("path","")
  if not isinstance(raw,str) or not raw:raise ValueError("missing screenshot path")
  candidate=Path(raw)
  if candidate.is_absolute():
   path=candidate.resolve()
  else:
   path=(root/candidate).resolve()
  if not path.is_relative_to(root) or not path.is_file():
   raise ValueError("missing or outside-root screenshot "+str(key))
  digest=sha256(path)
  if digest!=item.get("sha256") or path.stat().st_size!=item.get("size"):
   raise ValueError("SHA256/size mismatch for "+str(key))
  if digest in seen:raise ValueError("reused screenshot bytes: "+str(key))
  seen.add(digest)
  wh=check_png(path)
  report.append({"name":key,"path":str(path.relative_to(root)),
                 "sha256":digest,"size":path.stat().st_size,"resolution":wh,
                 "timestamp":item.get("timestamp"),
                 "visual_verdict":"NOT_REVIEWED"})
 return report

def write_gallery(root, items, dest):
 root=Path(root).resolve()
 dest=Path(dest).resolve()
 if not dest.parent.is_relative_to(root):
  raise ValueError("gallery must live inside screenshot evidence root")
 cards=[]
 for x in items:
  pic=(root/x["path"]).resolve()
  rel=pic.relative_to(dest.parent)
  # relative_to may fail for sibling folders; use os.path.relpath
  import os
  src=os.path.relpath(pic,dest.parent).replace(os.sep,"/")
  cards.append("<article><h2>"+html.escape(x["name"])+
   "</h2><img src='"+html.escape(src,quote=True)+
   "' alt='Screenshot requiring human inspection'><p>SHA256 "+
   x["sha256"]+"</p><p>Visual verdict: NOT REVIEWED</p></article>")
 page=("<!doctype html><meta charset='utf-8'><title>Physical Android evidence review</title>"
  "<style>body{background:#101827;color:#fff;font:16px system-ui;margin:25px}"
  "article{padding:20px;border-bottom:1px solid #555}img{max-width:100%;height:auto}"
  "p{overflow-wrap:anywhere}</style>"
  "<h1>NOT REVIEWED — Do not treat as gameplay PASS</h1>"
  "<p>Human reviewer must open each PNG and compare to the actual UI state, "
  "timestamps, TCP/logcat and PostgreSQL. Hash match is not visual proof.</p>"+
  "".join(cards))
 dest.write_text(page,encoding="utf-8")

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--root",required=True,help="Single immutable evidence run directory")
 p.add_argument("--manifest",required=True)
 p.add_argument("--gallery",default="visual_review.html")
 args=p.parse_args()
 root=Path(args.root).resolve()
 manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
 try:
  entries=verify(root,manifest)
  write_gallery(root,entries,root/args.gallery)
 except (OSError,ValueError,KeyError) as exc:
  print("EVIDENCE_GATE_FAILED:",exc,file=sys.stderr)
  return 2
 print(json.dumps({"integrity":"PASS","visual_review":"REQUIRED",
  "acceptance":"NOT_VERIFIED","screenshots":len(entries),
  "required_visual_states":REQUIRED},ensure_ascii=False,indent=2))
 return 0
if __name__=="__main__":raise SystemExit(main())
