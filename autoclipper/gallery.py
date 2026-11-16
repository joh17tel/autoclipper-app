"""Builds clips/index.html — one page to preview clips and copy captions."""
import glob
import html
import json
import os

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AutoClipper — Ready to post</title>
<style>
body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0f1115;color:#e8e8e8;margin:0;padding:20px}
h1{margin:0 0 4px;font-size:22px}.sub{color:#9aa0a6;margin-bottom:18px;font-size:14px}
.bar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.bar button{background:#22262e;color:#e8e8e8;border:1px solid #333;border-radius:8px;padding:6px 12px;cursor:pointer}
.bar button.on{background:#ffd400;color:#000;border-color:#ffd400}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{background:#181b21;border:1px solid #2a2e36;border-radius:12px;padding:12px}
.card.posted{opacity:.45}
.media{display:flex;gap:8px}.media video,.media img{width:50%;aspect-ratio:9/16;object-fit:cover;border-radius:8px;background:#000}
.meta{font-size:12px;color:#9aa0a6;margin:8px 0}
.hook{font-weight:700;font-size:15px;margin:6px 0}
.row{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.row button,.row a{font-size:12px;background:#2b3040;color:#fff;border:0;border-radius:6px;padding:7px 9px;cursor:pointer;text-decoration:none}
.row .yt{background:#c4302b}.row .tt{background:#111;border:1px solid #444}
label{font-size:13px;display:flex;align-items:center;gap:6px;margin-top:10px;cursor:pointer}
.chk{font-size:12px;margin:2px 0}.ok{color:#5ad17a}.bad{color:#ff6b6b;font-weight:700}
details{font-size:12px;color:#c9c9c9;margin-top:6px}details li{margin:3px 0}
.camp{display:inline-block;background:#ffd400;color:#000;font-size:11px;font-weight:700;border-radius:5px;padding:2px 6px;margin-bottom:6px}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#ffd400;color:#000;padding:8px 14px;border-radius:8px;display:none;font-weight:600}
</style></head><body>
<h1>Ready to post</h1>
<div class="sub">__COUNT__ clips · best first · tick "Posted" when done</div>
<div class="bar"><button id="fAll" class="on">All</button><button id="fNew">Not posted</button>
<select id="fCamp" style="background:#22262e;color:#e8e8e8;border:1px solid #333;border-radius:8px;padding:6px">__CAMPS__</select></div>
<div class="grid" id="grid">__CARDS__</div>
<div class="toast" id="toast">Copied!</div>
<script>
const DATA = __DATA__;
function copy(t){
  const done=()=>{const e=document.getElementById('toast');e.style.display='block';setTimeout(()=>e.style.display='none',900)};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(done,()=>fb(t,done))}else fb(t,done);
}
function fb(t,done){const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();
  try{document.execCommand('copy');done()}catch(e){}a.remove()}
function getPosted(){try{return JSON.parse(localStorage.getItem('posted')||'{}')}catch(e){return {}}}
function setPosted(p){try{localStorage.setItem('posted',JSON.stringify(p))}catch(e){}}
let filterNew=false;
function refresh(){const p=getPosted();const camp=document.getElementById('fCamp').value;
  document.querySelectorAll('.card').forEach(c=>{
  const id=c.dataset.id, on=!!p[id]; c.classList.toggle('posted',on);
  c.querySelector('input').checked=on;
  const hide=(filterNew&&on)||(camp&&c.dataset.camp!==camp);
  c.style.display=hide?'none':''})}
document.getElementById('fCamp').onchange=refresh;
document.querySelectorAll('.card').forEach(c=>{
  const d=DATA[c.dataset.id];
  const b1=c.querySelector('.cyt'),b2=c.querySelector('.cyd'),b3=c.querySelector('.ctt');
  if(b1)b1.onclick=()=>copy(d.youtube_title);
  if(b2)b2.onclick=()=>copy(d.youtube_description);
  if(b3)b3.onclick=()=>copy(d.tiktok_caption);
  c.querySelector('input').onchange=e=>{const p=getPosted();p[c.dataset.id]=e.target.checked;setPosted(p);refresh()};
});
fAll.onclick=()=>{filterNew=false;fAll.className='on';fNew.className='';refresh()};
fNew.onclick=()=>{filterNew=true;fNew.className='on';fAll.className='';refresh()};
refresh();
</script></body></html>"""

CARD = """<div class="card" data-id="{id}" data-camp="{camp}"><span class="camp">{camp}</span>
<div class="media"><video src="{video}" controls preload="metadata" poster="{thumb}"></video><img src="{thumb}" alt="thumbnail"></div>
<div class="hook">{hook}</div>
<div class="meta">{streamer} · {when} · {length}s · {layout} · score {score}</div>
<div class="row">{buttons}</div>{checks}{rules}
<div class="row"><a href="{video}" download>⬇ Video</a><a href="{thumb}" download>⬇ Thumbnail</a></div>
{reminder}<label><input type="checkbox"> Posted</label></div>"""


def build(out_dir: str) -> str:
    metas = []
    for mp in glob.glob(os.path.join(out_dir, "**", "meta.json"), recursive=True):
        try:
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
            m["_dir"] = os.path.relpath(os.path.dirname(mp), out_dir).replace("\\", "/")
            metas.append(m)
        except Exception:
            pass
    # newest stream first, then best score
    metas.sort(key=lambda m: (m.get("created", ""), m.get("score", 0)), reverse=True)
    data, cards, camps = {}, [], []
    for m in metas:
        cid = m["_dir"]
        data[cid] = {k: m[k] for k in ("youtube_title", "youtube_description", "tiktok_caption")}
        camp = m.get("campaign", "General")
        if camp not in camps:
            camps.append(camp)
        plats = m.get("platforms") or ["tiktok", "youtube"]
        btns = []
        if "youtube" in plats:
            btns += ['<button class="yt cyt">Copy YT title</button>',
                     '<button class="yt cyd">Copy YT description</button>']
        if "tiktok" in plats or "instagram" in plats:
            btns.append('<button class="tt ctt">Copy TikTok/IG caption</button>')
        chk = "".join(f'<div class="chk {"ok" if c["ok"] else "bad"}">{"✓" if c["ok"] else "✗ FIX:"} '
                      f'{html.escape(c["text"])}</div>' for c in m.get("checks", []))
        rules = m.get("manual_rules") or []
        rl = (f'<details><summary>Brief rules to check ({len(rules)})</summary><ul>'
              + "".join(f"<li>{html.escape(r)}</li>" for r in rules) + "</ul></details>") if rules else ""
        cards.append(CARD.format(camp=html.escape(camp), buttons="".join(btns), checks=chk, rules=rl,
            id=html.escape(cid), video=html.escape(f"{cid}/clip.mp4"),
            thumb=html.escape(f"{cid}/thumbnail.jpg"), hook=html.escape(m.get("hook", "")),
            streamer=html.escape(m.get("channel", "")), when=html.escape(m.get("created", "")[:16]),
            score=m.get("score", ""), length=m.get("length_sec", "?"),
            layout=html.escape(m.get("layout", "")),
            reminder=('<div class="meta" style="color:#ffd400">⚠ Turn on TikTok "Paid partnership" '
                      '/ YouTube "Paid promotion" when posting</div>') if m.get("disclosure") else ""))
    opts = '<option value="">All campaigns</option>' + "".join(
        f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in camps)
    page = (PAGE.replace("__COUNT__", str(len(metas))).replace("__CAMPS__", opts)
                .replace("__CARDS__", "\n".join(cards))
                .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path
