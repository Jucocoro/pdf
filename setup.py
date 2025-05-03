# setup.py
from setuptools import setup

APP = ['extract_questions_tkinter.py']
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'MyIcon.icns',
    'includes': ['tkinter','queue','threading','pdf2image','pytesseract','PIL'],
    'packages': ['pdf2image','pytesseract','PIL'],
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
