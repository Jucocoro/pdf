# setup.py
from setuptools import setup

APP = ['extract_questions_tkinter.py']
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'MyIcon.icns',       # 아까 만드신 .icns
    'packages': ['pdf2image','pytesseract','PIL'],
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
