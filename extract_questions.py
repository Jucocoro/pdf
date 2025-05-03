# 파일명: extract_questions.py

import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import PySimpleGUI as sg

# ----------------------------------------
# 유틸: 이미지 용량 500kb 이하로 자동 압축
def compress_image(file_path: str, target_size_kb=500):
    """JPEG로 재저장하면서 품질을 낮춰 500KB 이하로 압축."""
    img = Image.open(file_path)
    quality = 95
    while True:
        buf = tempfile.SpooledTemporaryFile()
        img.save(buf, format='JPEG', quality=quality)
        size = buf.tell() / 1024
        if size <= target_size_kb or quality <= 20:
            buf.seek(0)
            with open(file_path, 'wb') as f:
                f.write(buf.read())
            break
        quality -= 5

# ----------------------------------------
# 핵심: PDF → 페이지 이미지 → OCR 데이터 → 문항별 crop → 저장
def process_pdf(pdf_path: str, prefix: str, out_folder: str, fmt: str, window: sg.Window):
    try:
        pages = convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        window.write_event_value('-ERROR-', f"{pdf_path} 변환 실패: {e}")
        return

    for page_idx, page_img in enumerate(pages, start=1):
        # 페이지 전체 OCR (한글+영문)
        data = pytesseract.image_to_data(
            page_img, lang='kor+eng',
            output_type=pytesseract.Output.DICT
        )
        # “숫자.” 형태를 문항번호로 인식
        q_indexes = [
            i for i, txt in enumerate(data['text'])
            if re.match(r'^\d+\.$', txt.strip())
        ]
        # 다음 문항까지 영역을 crop
        for idx, q_i in enumerate(q_indexes):
            num = data['text'][q_i].rstrip('.')
            y1 = max(data['top'][q_i] - 10, 0)
            y2 = (
                data['top'][q_indexes[idx+1]] + data['height'][q_indexes[idx+1]] + 10
                if idx+1 < len(q_indexes)
                else page_img.height
            )
            cropped = page_img.crop((0, y1, page_img.width, y2))
            # 파일명: {prefix}-{문항번호(2자리)}.png 또는 .jpg
            num_str = num.zfill(2)
            out_name = f"{prefix}-{num_str}.{fmt}"
            out_path = os.path.join(out_folder, out_name)
            cropped.save(out_path, fmt.upper())
            # 용량 체크 및 압축
            if os.path.getsize(out_path) > 500 * 1024:
                compress_image(out_path)
            window.write_event_value('-PROGRESS-',
                                     f"[{pdf_path.name}] {out_name} 생성 완료")
    window.write_event_value('-DONE-', f"{pdf_path.name} 처리 완료")

# ----------------------------------------
# GUI 레이아웃 정의
sg.theme('SystemDefault')
layout = [
    [sg.Text('1) PDF 파일 선택'), sg.Input(key='-PDFS-'), sg.FilesBrowse(file_types=(("PDF","*.pdf"),))],
    [sg.Text('2) 파일별 접두어 (콤마 또는 줄바꿈으로 구분)'), sg.Multiline(size=(40,3), key='-PREFIX-')],
    [sg.Text('3) 출력 폴더 선택'), sg.Input(key='-OUT-'), sg.FolderBrowse()],
    [sg.Text('4) 이미지 형식'), sg.Combo(['png','jpg'], default_value='png', key='-FMT-')],
    [sg.Button('시작'), sg.Button('종료')],
    [sg.Multiline(size=(80,10), key='-LOG-', autoscroll=True, disabled=True)]
]
window = sg.Window('문제 이미지 추출 프로그램', layout)

# ----------------------------------------
# 이벤트 루프
while True:
    event, values = window.read()
    if event in (sg.WIN_CLOSED, '종료'):
        break
    if event == '시작':
        pdf_paths = [Path(p) for p in values['-PDFS-'].split(';') if p]
        prefixes = re.split(r'[,\n]+', values['-PREFIX-'].strip())
        out_folder = values['-OUT-']
        fmt = values['-FMT-']

        if not pdf_paths:
            sg.popup_error('PDF 파일을 하나 이상 선택하세요.')
            continue
        if len(prefixes) not in (1, len(pdf_paths)):
            sg.popup_error('접두어는 1개 또는 PDF 파일 수와 동일해야 합니다.')
            continue
        # output 폴더 생성
        os.makedirs(out_folder, exist_ok=True)

        # 백그라운드 스레드에서 처리
        def worker():
            for i, pdf in enumerate(pdf_paths):
                pre = prefixes[i] if len(prefixes)>1 else prefixes[0]
                process_pdf(str(pdf), pre, out_folder, fmt, window)
            window.write_event_value('-ALL_DONE-', '모든 작업이 완료되었습니다.')

        threading.Thread(target=worker, daemon=True).start()

    # 백그라운드 로그 수신
    if event == '-PROGRESS-':
        window['-LOG-'].print(values[event])
    if event == '-ERROR-':
        window['-LOG-'].print('ERROR: '+values[event])
    if event == '-DONE-':
        window['-LOG-'].print(values[event])
    if event == '-ALL_DONE-':
        window['-LOG-'].print(values[event])
        sg.popup('완료', '모든 PDF 처리 완료!')

window.close()
