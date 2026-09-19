from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import Tk, StringVar, BooleanVar, filedialog, messagebox
from tkinter import ttk

import pdfplumber
import requests
from pypdf import PdfReader, PdfWriter


APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "GVNBordro"
OUT_DIR = APP_DIR / "Bordrolar"
DB_PATH = APP_DIR / "gvn_bordro.db"
SETTINGS_PATH = APP_DIR / "ayarlar.json"
APP_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

RED = "#d71920"
DARK = "#141820"
PANEL = "#202630"
TEXT = "#f4f5f7"
MUTED = "#9ca6b5"


@dataclass
class Payroll:
    page: int
    name: str
    phone: str
    period: str
    path: str = ""
    selected: bool = True
    status: str = "Hazır"


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = "90" + digits[1:]
    elif len(digits) == 10 and digits.startswith("5"):
        digits = "90" + digits
    return digits


def find_phone(text: str) -> str:
    labels = r"(?:telefon|gsm|cep|whatsapp|tel)"
    labeled = re.search(labels + r"\s*(?:no|numarası)?\s*[:\-]?\s*(\+?90\s*5\d{2}[\s.()-]*\d{3}[\s.()-]*\d{2}[\s.()-]*\d{2}|0?5\d{2}[\s.()-]*\d{3}[\s.()-]*\d{2}[\s.()-]*\d{2})", text, re.I)
    if labeled:
        return normalize_phone(labeled.group(1))
    general = re.search(r"(?<!\d)(?:\+?90\s*)?0?5\d{2}[\s.()-]*\d{3}[\s.()-]*\d{2}[\s.()-]*\d{2}(?!\d)", text)
    return normalize_phone(general.group(0)) if general else ""


def parse_page(text: str, page_no: int) -> Payroll:
    name = ""
    row = re.search(r"^\s*\d+\s+([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ ]{3,}?)\s+\d{2}\.\d{2}\.\d{4}", text, re.M)
    if row:
        name = row.group(1).strip()
    if not name:
        first = re.search(r"^\s*Adı\s*:\s*([A-ZÇĞİÖŞÜ ]+?)(?:\s{2,}|$)", text, re.I | re.M)
        last = re.search(r"^\s*Soyadı\s*:\s*([A-ZÇĞİÖŞÜ ]+?)(?:\s{2,}|$)", text, re.I | re.M)
        if first and last:
            name = f"{first.group(1).strip()} {last.group(1).strip()}"
    if not name:
        name = f"Personel {page_no}"
    period_m = re.search(r"Bordro Tar\.\s*:\s*([A-ZÇĞİÖŞÜ]+\s*/\s*\d{4})", text, re.I)
    period = re.sub(r"\s*/\s*", "/", period_m.group(1).strip()) if period_m else ""
    return Payroll(page_no, " ".join(name.split()), find_phone(text), period)


class Database:
    def __init__(self):
        self.db = sqlite3.connect(DB_PATH)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS contacts(name TEXT PRIMARY KEY, phone TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sends(id INTEGER PRIMARY KEY, sent_at TEXT, name TEXT, phone TEXT,
          period TEXT, file_path TEXT, result TEXT, detail TEXT);
        """)
        self.db.commit()

    def phone_for(self, name: str) -> str:
        row = self.db.execute("SELECT phone FROM contacts WHERE name=?", (name,)).fetchone()
        return row[0] if row else ""

    def remember(self, name: str, phone: str):
        self.db.execute("INSERT INTO contacts(name,phone) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET phone=excluded.phone", (name, phone))
        self.db.commit()

    def log(self, item: Payroll, result: str, detail: str = ""):
        self.db.execute("INSERT INTO sends(sent_at,name,phone,period,file_path,result,detail) VALUES(?,?,?,?,?,?,?)",
                        (datetime.now().isoformat(timespec="seconds"), item.name, item.phone, item.period, item.path, result, detail))
        self.db.commit()


class CloudApi:
    def __init__(self, settings: dict):
        self.s = settings
        self.base = f"https://graph.facebook.com/{settings.get('api_version','v23.0')}"

    def _headers(self):
        return {"Authorization": f"Bearer {self.s['access_token']}"}

    def upload(self, path: str) -> str:
        url = f"{self.base}/{self.s['phone_number_id']}/media"
        with open(path, "rb") as fh:
            res = requests.post(url, headers=self._headers(), data={"messaging_product": "whatsapp"},
                                files={"file": (Path(path).name, fh, "application/pdf")}, timeout=90)
        res.raise_for_status()
        return res.json()["id"]

    def send_template_document(self, phone: str, media_id: str, filename: str):
        payload = {
            "messaging_product": "whatsapp", "to": phone, "type": "template",
            "template": {
                "name": self.s["template_name"],
                "language": {"code": self.s.get("template_language", "tr")},
                "components": [{"type": "header", "parameters": [{"type": "document", "document": {"id": media_id, "filename": filename}}]}]
            }
        }
        res = requests.post(f"{self.base}/{self.s['phone_number_id']}/messages", headers={**self._headers(), "Content-Type": "application/json"}, json=payload, timeout=60)
        res.raise_for_status()
        return res.json()


class App(Tk):
    def __init__(self):
        super().__init__()
        self.title("GVN Bordro")
        self.geometry("1240x760")
        self.minsize(1050, 650)
        self.configure(bg=DARK)
        self.dbx = Database()
        self.items: list[Payroll] = []
        self.source_pdf = ""
        self.settings = self.load_settings()
        self.status_var = StringVar(value="Bordro PDF dosyanızı seçerek başlayın.")
        self.make_style()
        self.make_ui()

    def load_settings(self):
        defaults = {"mode": "cloud", "api_version": "v23.0", "phone_number_id": "", "access_token": "", "template_name": "gvn_bordro", "template_language": "tr"}
        if SETTINGS_PATH.exists():
            try: defaults.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
            except Exception: pass
        return defaults

    def make_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", font=("Segoe UI", 10))
        s.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL, rowheight=34, borderwidth=0)
        s.configure("Treeview.Heading", background="#2c3440", foreground=TEXT, relief="flat", font=("Segoe UI Semibold", 10))
        s.map("Treeview", background=[("selected", RED)])
        s.configure("Red.TButton", background=RED, foreground="white", padding=(18, 10), borderwidth=0)
        s.map("Red.TButton", background=[("active", "#b9151b")])
        s.configure("Dark.TButton", background="#303946", foreground="white", padding=(14, 9), borderwidth=0)

    def make_ui(self):
        sidebar = ttk.Frame(self, width=215)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        logo = ttk.Label(sidebar, text=" B ", foreground="white", background=RED, font=("Segoe UI Black", 30))
        logo.pack(pady=(30, 8))
        ttk.Label(sidebar, text="GVN BORDRO", font=("Segoe UI Semibold", 17)).pack(pady=(0, 30))
        ttk.Label(sidebar, text="Güvenli bordro dağıtımı", foreground=MUTED).pack()
        ttk.Separator(sidebar).pack(fill="x", padx=22, pady=24)
        ttk.Button(sidebar, text="PDF Bordro Seç", style="Red.TButton", command=self.choose_pdf).pack(fill="x", padx=18, pady=6)
        ttk.Button(sidebar, text="Ayarlar", style="Dark.TButton", command=self.settings_dialog).pack(fill="x", padx=18, pady=6)
        ttk.Button(sidebar, text="Çıktı Klasörü", style="Dark.TButton", command=lambda: os.startfile(OUT_DIR) if os.name == "nt" else None).pack(fill="x", padx=18, pady=6)

        main = ttk.Frame(self, padding=24)
        main.pack(side="left", fill="both", expand=True)
        top = ttk.Frame(main)
        top.pack(fill="x")
        ttk.Label(top, text="Aylık Bordro Dağıtımı", font=("Segoe UI Semibold", 23)).pack(side="left")
        self.summary = ttk.Label(top, text="0 bordro", foreground=MUTED, font=("Segoe UI", 12))
        self.summary.pack(side="right")
        ttk.Label(main, textvariable=self.status_var, foreground=MUTED).pack(anchor="w", pady=(4, 18))

        cols = ("page", "name", "phone", "period", "status")
        self.tree = ttk.Treeview(main, columns=cols, show="headings", selectmode="extended")
        headers = [("page", "Sayfa", 60), ("name", "Personel", 300), ("phone", "WhatsApp", 170), ("period", "Dönem", 160), ("status", "Durum", 130)]
        for key, label, width in headers:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.edit_phone)

        bottom = ttk.Frame(main)
        bottom.pack(fill="x", pady=(16, 0))
        ttk.Button(bottom, text="Telefonu Düzenle", style="Dark.TButton", command=self.edit_phone).pack(side="left")
        ttk.Button(bottom, text="Seçilenleri Gönder", style="Red.TButton", command=self.send_selected).pack(side="right")

    def choose_pdf(self):
        path = filedialog.askopenfilename(title="Bordro PDF seç", filetypes=[("PDF", "*.pdf")])
        if not path: return
        self.source_pdf = path
        self.status_var.set("PDF okunuyor, personeller hazırlanıyor...")
        threading.Thread(target=self.parse_pdf, daemon=True).start()

    def parse_pdf(self):
        parsed = []
        try:
            with pdfplumber.open(self.source_pdf) as pdf:
                for ix, page in enumerate(pdf.pages, 1):
                    item = parse_page(page.extract_text() or "", ix)
                    if not item.phone: item.phone = self.dbx.phone_for(item.name)
                    parsed.append(item)
            self.items = parsed
            self.after(0, self.refresh)
            self.after(0, lambda: self.status_var.set(f"{len(parsed)} bordro bulundu. Eksik telefonları çift tıklayarak girin."))
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("PDF okunamadı", str(exc)))

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, x in enumerate(self.items):
            phone = "+" + x.phone if x.phone else "Telefon eksik"
            self.tree.insert("", "end", iid=str(i), values=(x.page, x.name, phone, x.period, x.status))
        ready = sum(bool(x.phone) for x in self.items)
        self.summary.config(text=f"{len(self.items)} bordro  •  {ready} telefon hazır")

    def edit_phone(self, _event=None):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0]); item = self.items[idx]
        win = ttk.Frame(self, padding=20)
        dialog = __import__("tkinter").Toplevel(self)
        dialog.title("Telefonu Düzenle"); dialog.geometry("410x190"); dialog.transient(self); dialog.grab_set()
        win = ttk.Frame(dialog, padding=20); win.pack(fill="both", expand=True)
        ttk.Label(win, text=item.name, font=("Segoe UI Semibold", 13)).pack(anchor="w")
        value = StringVar(value=("+" + item.phone) if item.phone else "+90")
        entry = ttk.Entry(win, textvariable=value, font=("Segoe UI", 12)); entry.pack(fill="x", pady=16); entry.focus()
        def save():
            phone = normalize_phone(value.get())
            if not re.fullmatch(r"90\d{10}", phone):
                messagebox.showwarning("Telefon", "Numarayı 05XX XXX XX XX biçiminde girin."); return
            item.phone = phone; self.dbx.remember(item.name, phone); dialog.destroy(); self.refresh()
        ttk.Button(win, text="Kaydet", style="Red.TButton", command=save).pack(side="right")

    def split_item(self, item: Payroll):
        period = re.sub(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü_-]+", "_", item.period or "Bordro")
        name = re.sub(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü_-]+", "_", item.name)
        folder = OUT_DIR / period; folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{name}_{period}.pdf"
        reader = PdfReader(self.source_pdf); writer = PdfWriter(); writer.add_page(reader.pages[item.page - 1])
        with open(target, "wb") as fh: writer.write(fh)
        item.path = str(target)

    def send_selected(self):
        indices = [int(x) for x in self.tree.selection()] or list(range(len(self.items)))
        chosen = [self.items[i] for i in indices]
        missing = [x.name for x in chosen if not x.phone]
        if missing:
            messagebox.showwarning("Telefon eksik", f"{len(missing)} personelin telefonu eksik. Önce telefonları girin.")
            return
        if not messagebox.askyesno("Gönderim onayı", f"{len(chosen)} personele bordro gönderilecek. Devam edilsin mi?"): return
        threading.Thread(target=self.send_worker, args=(chosen,), daemon=True).start()

    def send_worker(self, chosen):
        mode = self.settings.get("mode", "cloud")
        api = CloudApi(self.settings) if mode == "cloud" else None
        for n, item in enumerate(chosen, 1):
            try:
                self.after(0, lambda i=item, n=n: self.status_var.set(f"Gönderiliyor ({n}/{len(chosen)}): {i.name}"))
                self.split_item(item)
                if mode == "cloud":
                    if not self.settings.get("phone_number_id") or not self.settings.get("access_token"):
                        raise ValueError("WhatsApp Cloud API ayarları eksik.")
                    media_id = api.upload(item.path)
                    api.send_template_document(item.phone, media_id, Path(item.path).name)
                    item.status = "Gönderildi"; self.dbx.log(item, "Gönderildi")
                else:
                    msg = f"Sayın {item.name}, {item.period} dönemine ait ücret bordronuz hazırlanmıştır."
                    webbrowser.open(f"https://wa.me/{item.phone}?text={requests.utils.quote(msg)}")
                    item.status = "WhatsApp açıldı"; self.dbx.log(item, "WhatsApp açıldı", "PDF kullanıcı tarafından eklenir")
            except Exception as exc:
                item.status = "Hata"; self.dbx.log(item, "Hata", str(exc))
            self.after(0, self.refresh)
        self.after(0, lambda: self.status_var.set("Gönderim işlemi tamamlandı. Durum sütununu kontrol edin."))

    def settings_dialog(self):
        import tkinter as tk
        d = tk.Toplevel(self); d.title("GVN Bordro Ayarları"); d.geometry("590x470"); d.transient(self); d.grab_set()
        f = ttk.Frame(d, padding=22); f.pack(fill="both", expand=True)
        ttk.Label(f, text="WhatsApp Gönderim Ayarları", font=("Segoe UI Semibold", 17)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0,18))
        mode = StringVar(value=self.settings.get("mode", "cloud"))
        ttk.Radiobutton(f, text="Tam otomatik - WhatsApp Business Cloud API", variable=mode, value="cloud").grid(row=1,column=0,columnspan=2,sticky="w")
        ttk.Radiobutton(f, text="Yardımlı - WhatsApp Web sohbetini aç", variable=mode, value="web").grid(row=2,column=0,columnspan=2,sticky="w",pady=(4,16))
        fields = [("phone_number_id","Telefon numarası kimliği"),("access_token","Kalıcı erişim anahtarı"),("template_name","Onaylı şablon adı"),("template_language","Şablon dili"),("api_version","Graph API sürümü")]
        vars_ = {}
        for row,(key,label) in enumerate(fields,3):
            ttk.Label(f,text=label).grid(row=row,column=0,sticky="w",pady=7)
            vars_[key]=StringVar(value=self.settings.get(key,""))
            ttk.Entry(f,textvariable=vars_[key],show="•" if key=="access_token" else "").grid(row=row,column=1,sticky="ew",padx=(18,0),pady=7)
        f.columnconfigure(1,weight=1)
        ttk.Label(f,text="Not: Tam otomatik gönderim için Meta panelinde belge başlıklı bir şablon onaylanmalıdır.",foreground=MUTED,wraplength=520).grid(row=8,column=0,columnspan=2,sticky="w",pady=15)
        def save():
            self.settings["mode"]=mode.get()
            for k,v in vars_.items(): self.settings[k]=v.get().strip()
            SETTINGS_PATH.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding="utf-8")
            d.destroy(); self.status_var.set("Ayarlar kaydedildi.")
        ttk.Button(f,text="Ayarları Kaydet",style="Red.TButton",command=save).grid(row=9,column=1,sticky="e")


if __name__ == "__main__":
    App().mainloop()
