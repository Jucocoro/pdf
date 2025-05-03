#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 한국사·수능 문제지 → 문항 단위 이미지 자동 잘라내기
작성 : 2025-05-04 (헤더·푸터 제거, 좌/우 반분 후 문항 단위 크롭)
- 컬럼 분할 없이 문제 하나를 텍스트·보기·이미지 블록 묶음으로 크롭
- num → ①~⑤ 옵션 블록 묶음 인식하여 정확한 범위 산정
- 텍스트 + 보기 + 이미지 모두 빠짐없이 저장
- 슬림 여백 적용
"""
import os
import re
import sys
import queue
import threading
import tempfile
import subprocess
from pathlib import Path
from collections import defaultdict

import fitz      # pip install pymupdf
from PIL import Image, ImageTk  # pip install pillow

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ──────────────────────────────────────
RE_NUM    = re.compile(r'^(?:\(|\[)?\s*(\d{1,2})(?:\.|\))')  # 문항 번호
RE_OPTION = re.compile(r'[①-⑤]')                            # 보기 기호

def compress_jpeg(fp: str, target_kb: int = 500) -> None:
    """JPEG이 너무 크면 품질 낮춰 재압축"""
    try:
        img = Image.open(fp)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        for q in range(95, 9, -5):
            buf = tempfile.SpooledTemporaryFile()
            img.save(buf, 'JPEG', quality=q)
            if buf.tell() <= target_kb * 1024:
                buf.seek(0)
                with open(fp, 'wb') as f:
                    f.write(buf.read())
                return
    except Exception:
        pass

def process_pdf(pdf_path: str, prefix: str, out_folder: str, fmt: str, log: queue.Queue):
    basename = Path(pdf_path).stem
    log.put(("log", f"[{basename}] 처리 시작"))
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        log.put(("log", f"[ERR] '{basename}' 열기 실패: {e}"))
        return

    for pnum, page in enumerate(doc, start=1):
        try:
            pd = page.get_text("dict")
            raw = pd["blocks"]
        except Exception:
            log.put(("log", f"[{basename}] p{pnum} 블록 추출 실패"))
            continue

        # 텍스트 블록만
        text_blocks = []
        for b in raw:
            if b["type"] != 0:
                continue
            x0, y0, x1, y1 = b["bbox"]
            txt = "".join(span["text"] for line in b["lines"] for span in line["spans"]).strip()
            text_blocks.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "txt": txt})

        # 문항 번호만
        qblocks = [b for b in text_blocks if RE_NUM.match(b["txt"])]
        qblocks.sort(key=lambda b: b["y0"])
        if not qblocks:
            log.put(("log", f"[{basename}] p{pnum}: 번호 미검출"))
            continue

        # 여백 및 페이지 크기
        v_margin = 8
        h_margin = 8
        pw, ph = page.rect.width, page.rect.height
        midx = pw / 2.0
        dupe = defaultdict(int)

        left_q  = [b for b in qblocks if b["x1"] <= midx]
        right_q = [b for b in qblocks if b["x0"] >= midx]

        for side, qlist in (("L", left_q), ("R", right_q)):
            if not qlist:
                continue
            if side == "L":
                crop_x0, crop_x1 = h_margin, midx - h_margin
            else:
                crop_x0, crop_x1 = midx + h_margin, pw - h_margin

            for idx, qb in enumerate(qlist):
                m = RE_NUM.match(qb["txt"])
                if not m:
                    continue
                num = m.group(1).zfill(2)
                dupe[num] += 1
                suffix = f"-dup{dupe[num]-1}" if dupe[num] > 1 else ""
                crop_y0 = max(0, qb["y0"] - v_margin)
                y_next = qlist[idx+1]["y0"] if idx+1 < len(qlist) else ph
                opts = [
                    b for b in text_blocks
                    if RE_OPTION.search(b["txt"])
                    and b["y0"] >= qb["y0"]
                    and b["y1"] <= y_next
                ]
                crop_y1 = (min(ph, max(o["y1"] for o in opts) + v_margin)
                           if opts else min(ph, y_next - v_margin))

                clip = fitz.Rect(crop_x0, crop_y0, crop_x1, crop_y1)
                try:
                    pix = page.get_pixmap(clip=clip, dpi=300)
                except Exception:
                    log.put(("log", f"[{basename}] p{pnum} {side}-{num} 렌더 실패"))
                    continue

                fname = f"{prefix}-{num}{suffix}.{fmt}"
                outp = os.path.join(out_folder, fname)
                try:
                    pix.save(outp)
                    if fmt == "jpg" and os.path.getsize(outp) > 500*1024:
                        compress_jpeg(outp)
                    log.put(("log", f"[{basename}] p{pnum} ▶ {fname}"))
                    log.put(("thumb", outp))
                except Exception as e:
                    log.put(("log", f"[ERR] {fname} 저장 실패: {e}"))

    log.put(("log", f"[{basename}] 완료"))

# ──────────────────────────────────────
#### 이하 GUI 부분 ####

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("문제 커팅기")
        self.geometry("900x700")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # 1) PDF 선택
        tk.Label(self, text="1) PDF 파일 선택").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.pdf = tk.Entry(self, width=80);   self.pdf.grid(row=0, column=1, sticky="we", padx=4)
        tk.Button(self, text="Browse", command=self.sel_pdf).grid(row=0, column=2)

        # 2) 접두어
        tk.Label(self, text="2) 접두어").grid(row=1, column=0, sticky="w", padx=8)
        self.pref = tk.Text(self, height=2);    self.pref.grid(row=1, column=1, columnspan=2, sticky="we", padx=4)

        # 3) 출력 폴더
        tk.Label(self, text="3) 출력 폴더").grid(row=2, column=0, sticky="w", padx=8)
        self.out  = tk.Entry(self, width=80);   self.out.grid(row=2, column=1, sticky="we", padx=4)
        tk.Button(self, text="Browse", command=self.sel_out).grid(row=2, column=2)

        # 4) 이미지 형식
        tk.Label(self, text="4) 이미지 형식").grid(row=3, column=0, sticky="w", padx=8)
        self.fmt = ttk.Combobox(self, values=["png","jpg"], state="readonly", width=10)
        self.fmt.current(0);                    self.fmt.grid(row=3, column=1, sticky="w", padx=4)

        # 시작/종료 버튼 프레임
        bf = tk.Frame(self); bf.grid(row=4, column=1, sticky="e", pady=8)
        self.btn = tk.Button(bf, text="시작", command=self.start); self.btn.pack(side="left", padx=5)
        tk.Button(bf, text="종료", command=self.destroy).pack(side="left", padx=5)

        # 로그
        tk.Label(self, text="로그").grid(row=5, column=0, sticky="nw", padx=8)
        self.log = scrolledtext.ScrolledText(self, state="disabled", height=15)
        self.log.grid(row=5, column=1, columnspan=2, sticky="nsew", padx=8, pady=4)

        # 썸네일 영역
        tk.Label(self, text="썸네일").grid(row=6, column=0, sticky="w", padx=8)
        self.canvas = tk.Canvas(self, height=140, bg="#f0f0f0")
        self.canvas.grid(row=7, column=0, columnspan=3, sticky="we", padx=8)
        sb = tk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        sb.grid(row=8, column=0, columnspan=3, sticky="we")
        self.canvas.configure(xscrollcommand=sb.set)
        self.tf = tk.Frame(self.canvas)
        self.canvas.create_window((0,0), window=self.tf, anchor="nw")
        self.tf.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.thumbs = []
        self.q = queue.Queue()
        self.after(100, self.poll)

    def sel_pdf(self):
        fs = filedialog.askopenfilenames(filetypes=[("PDF","*.pdf")])
        if fs:
            self.pdf.delete(0, tk.END)
            self.pdf.insert(0, ";".join(fs))

    def sel_out(self):
        d = filedialog.askdirectory()
        if d:
            self.out.delete(0, tk.END)
            self.out.insert(0, d)

    def log_put(self, msg):
        self.log.configure(state="normal")
        self.log.insert(tk.END, msg+"\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def add_thumb(self, path):
        im = Image.open(path)
        im.thumbnail((120,120), Image.Resampling.LANCZOS)
        ph = ImageTk.PhotoImage(im)
        lbl = tk.Label(self.tf, image=ph, cursor="hand2")
        lbl.image = ph
        lbl.pack(side="left", padx=4, pady=4)
        lbl.bind("<Button-1>", lambda e, p=path: self.open_folder(p))
        self.thumbs.append(ph)

    def open_folder(self, path):
        """썸네일 클릭 시 해당 파일의 폴더(또는 파일 자체 위치)를 엽니다."""
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", path])
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", path])
        else:
            # Linux 등
            subprocess.run(["xdg-open", os.path.dirname(path)])

    def poll(self):
        while not self.q.empty():
            key, val = self.q.get_nowait()
            if key == "log":
                self.log_put(val)
            elif key == "thumb":
                self.add_thumb(val)
            elif key == "enable":
                self.btn.config(state="normal")
        self.after(100, self.poll)

    def start(self):
        pdfs  = [p for p in self.pdf.get().split(";") if p]
        prefs = [x for x in re.split(r'[,\n]+', self.pref.get("1.0","end")) if x]
        outd  = self.out.get().strip()
        fmt   = self.fmt.get()
        if not pdfs:
            return messagebox.showerror("ERR", "PDF 선택")
        if not prefs:
            return messagebox.showerror("ERR", "접두어 입력")
        if len(prefs) not in (1, len(pdfs)):
            return messagebox.showerror("ERR", "접두어 수 오류")
        if not outd:
            return messagebox.showerror("ERR", "출력 폴더 선택")

        for w in self.tf.winfo_children():
            w.destroy()
        self.thumbs.clear()
        self.log_put("=== 작업 시작 ===")
        self.btn.config(state="disabled")

        def worker():
            for i, p in enumerate(pdfs):
                pre = prefs[i] if len(prefs)>1 else prefs[0]
                tgt = os.path.join(outd, pre)
                os.makedirs(tgt, exist_ok=True)
                process_pdf(p, pre, tgt, fmt, self.q)
            self.q.put(("log","=== 완료 ==="))
            self.q.put(("enable",None))

        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    missing = []
    for m,pkg in [("fitz","PyMuPDF"), ("PIL","Pillow")]:
        try: __import__(m)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("필요 패키지:", ", ".join(missing))
        sys.exit(1)
    App().mainloop()
