#!/usr/bin/env python3
import os
import re
import sys
import threading
import queue
import tempfile
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import os, sys

if getattr(sys, 'frozen', False):
    # brew 설치 경로 추가
    os.environ['PATH'] += os.pathsep + '/usr/local/bin' + os.pathsep + '/opt/homebrew/bin'

# ——————————————————————————————————————————
# 500KB 초과 시 JPEG 재압축
def compress_image(file_path: str, target_size_kb=500):
    img = Image.open(file_path)
    quality = 95
    while True:
        buf = tempfile.SpooledTemporaryFile()
        img.save(buf, format='JPEG', quality=quality)
        size_kb = buf.tell() / 1024
        if size_kb <= target_size_kb or quality <= 20:
            buf.seek(0)
            with open(file_path, 'wb') as f:
                f.write(buf.read())
            break
        quality -= 5

# ——————————————————————————————————————————
# 실제 PDF 처리 함수 (스레드에서 실행)
def process_pdf(pdf_path, prefix, out_folder, fmt, log_queue):
    basename = Path(pdf_path).stem
    try:
        pages = convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        log_queue.put(("log", f"ERROR: '{basename}' 변환 실패: {e}"))
        return

    for page_number, page in enumerate(pages, start=1):
        data = pytesseract.image_to_data(
            page, lang='kor+eng', output_type=pytesseract.Output.DICT
        )
        # “숫자.” 패턴 찾기
        q_idxs = [i for i, t in enumerate(data['text']) if re.match(r'^\d+\.$', t)]
        nums = [data['text'][i].rstrip('.') for i in q_idxs]

        # 오류 감지: 미검출
        if not q_idxs:
            log_queue.put(("log", f"[{basename}] 페이지 {page_number} 번호 인식 실패"))
        # 오류 감지: 중복
        duplicates = [n for n in set(nums) if nums.count(n) > 1]
        if duplicates:
            log_queue.put(("log", f"[{basename}] 페이지 {page_number} 중복 번호: {', '.join(duplicates)}"))

        for idx, qi in enumerate(q_idxs):
            num = data['text'][qi].rstrip('.')
            y1 = max(data['top'][qi] - 10, 0)
            if idx + 1 < len(q_idxs):
                next_qi = q_idxs[idx+1]
                y2 = data['top'][next_qi] + data['height'][next_qi] + 10
            else:
                y2 = page.height

            crop = page.crop((0, y1, page.width, y2))

            num_str = num.zfill(2)
            out_name = f"{prefix}-{num_str}.{fmt}"
            out_path = os.path.join(out_folder, out_name)

            # PNG/JPEG 내부 포맷 지정
            pil_fmt = "JPEG" if fmt.lower()=="jpg" else "PNG"
            crop.save(out_path, pil_fmt)

            # 용량 체크
            if os.path.getsize(out_path) > 500*1024:
                compress_image(out_path)

            # 로그와 썸네일 큐에 추가
            log_queue.put(("log", f"[{basename}] → {out_name}"))
            log_queue.put(("thumb", out_path))

    log_queue.put(("log", f"'{basename}' 처리 완료"))

# ——————————————————————————————————————————
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("문제 이미지 추출 (Tkinter)")
        self.geometry("900x700")

        # 1) PDF 선택
        tk.Label(self, text="1) PDF 파일 선택").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.pdf_entry = tk.Entry(self, width=60)
        self.pdf_entry.grid(row=0, column=1, padx=4)
        tk.Button(self, text="Browse", command=self.select_pdfs).grid(row=0, column=2, padx=4)

        # 2) 접두어
        tk.Label(self, text="2) 파일 접두어 (콤마/줄바꿈 구분)").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.pref_txt = tk.Text(self, height=2, width=56)
        self.pref_txt.grid(row=1, column=1, columnspan=2, padx=4)

        # 3) 출력 폴더
        tk.Label(self, text="3) 출력 폴더 선택").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.out_entry = tk.Entry(self, width=60)
        self.out_entry.grid(row=2, column=1, padx=4)
        tk.Button(self, text="Browse", command=self.select_out).grid(row=2, column=2, padx=4)

        # 4) 이미지 형식
        tk.Label(self, text="4) 이미지 형식").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.fmt_combo = ttk.Combobox(self, values=["png","jpg"], width=10)
        self.fmt_combo.current(0)
        self.fmt_combo.grid(row=3, column=1, sticky="w", padx=4)

        # 시작/종료 버튼
        tk.Button(self, text="시작", command=self.start).grid(row=4, column=1, sticky="e", pady=8)
        tk.Button(self, text="종료", command=self.destroy).grid(row=4, column=2, sticky="w", pady=8)

        # 로그 출력
        self.log = scrolledtext.ScrolledText(self, state="disabled", width=110, height=15)
        self.log.grid(row=5, column=0, columnspan=3, padx=8, pady=4)

        # 썸네일 프리뷰
        tk.Label(self, text="미리보기 (썸네일)").grid(row=6, column=0, sticky="w", padx=8)
        self.thumb_canvas = tk.Canvas(self, height=140)
        self.thumb_canvas.grid(row=7, column=0, columnspan=3, sticky="we", padx=8)
        self.thumb_scroll = tk.Scrollbar(self, orient="horizontal", command=self.thumb_canvas.xview)
        self.thumb_scroll.grid(row=8, column=0, columnspan=3, sticky="we")
        self.thumb_canvas.configure(xscrollcommand=self.thumb_scroll.set)
        self.thumb_frame = tk.Frame(self.thumb_canvas)
        self.thumb_canvas.create_window((0,0), window=self.thumb_frame, anchor="nw")
        self.thumbs = []  # PhotoImage 레퍼런스 보관
        self.thumb_frame.bind(
            "<Configure>",
            lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))
        )

        # 스레드 간 통신 큐
        self.log_queue = queue.Queue()
        self.check_queue()

    def select_pdfs(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF Files","*.pdf")])
        if files:
            self.pdf_entry.delete(0,tk.END)
            self.pdf_entry.insert(0, ";".join(files))

    def select_out(self):
        folder = filedialog.askdirectory()
        if folder:
            self.out_entry.delete(0,tk.END)
            self.out_entry.insert(0, folder)

    def log_print(self, msg):
        self.log.configure(state="normal")
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def add_thumbnail(self, img_path):
        img = Image.open(img_path)
        img.thumbnail((120,120))
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(self.thumb_frame, image=photo)
        lbl.image = photo
        lbl.pack(side="left", padx=4, pady=4)
        self.thumbs.append(photo)

    def check_queue(self):
        try:
            while True:
                ev = self.log_queue.get_nowait()
                kind, val = ev
                if kind == "log":
                    self.log_print(val)
                elif kind == "thumb":
                    self.add_thumbnail(val)
        except queue.Empty:
            pass
        finally:
            self.after(100, self.check_queue)

    def start(self):
        pdfs = [p for p in self.pdf_entry.get().split(";") if p.strip()]
        prefixes = re.split(r'[,\n]+', self.pref_txt.get("1.0",tk.END).strip())
        out_parent = self.out_entry.get().strip()
        fmt = self.fmt_combo.get()

        if not pdfs:
            messagebox.showerror("Error","PDF 파일을 하나 이상 선택하세요.")
            return
        if len(prefixes) not in (1, len(pdfs)):
            messagebox.showerror("Error","접두어는 1개이거나 PDF 수와 같아야 합니다.")
            return
        if not out_parent or not os.path.isdir(out_parent):
            messagebox.showerror("Error","유효한 출력 폴더를 선택하세요.")
            return

        def worker():
            for idx, pdf in enumerate(pdfs):
                pre = prefixes[idx] if len(prefixes)>1 else prefixes[0]
                # 접두어별 하위 폴더
                target_dir = os.path.join(out_parent, pre)
                os.makedirs(target_dir, exist_ok=True)
                process_pdf(pdf, pre, target_dir, fmt, self.log_queue)
            self.log_queue.put(("log","모든 PDF 처리 완료!"))
            # 완료 알림
            messagebox.showinfo("완료","모든 PDF 처리 작업이 완료되었습니다.")
        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    # PyInstaller 번들용 Tesseract 경로 예시 (필요 시 활성화)
    # import pytesseract, os, sys
    # if getattr(sys, 'frozen', False):
    #     base = sys._MEIPASS
    # else:
    #     base = os.path.dirname(__file__)
    # pytesseract.pytesseract.tesseract_cmd = os.path.join(base, 'tesseract.exe')

    app = App()
    app.mainloop()
