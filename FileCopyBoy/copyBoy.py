#!/usr/bin/env python3
# file_selector_app.py

import os
import sys
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

class FileSelectorApp:
    def __init__(self):
        # CONFIG WAHLEN (mehrere INIs möglich)
        cfg_path = filedialog.askopenfilename(
            title="Config-Datei wählen",
            filetypes=[("INI Dateien","*.ini"),("Alle Dateien","*.*")]
        )
        if not cfg_path:
            messagebox.showerror("Fehler", "Keine Config ausgewählt – Programm beendet.")
            sys.exit(1)
        cfg = configparser.ConfigParser()
        cfg.read(cfg_path)
        s = cfg['Settings']
        self.root_folder = Path(s.get('root_folder', '.')).expanduser().resolve()
        # Excludes aus Config
        self.excl_folders = {n.strip() for n in s.get('exclude_folders','').split(',') if n.strip()}
        self.excl_files   = {n.strip() for n in s.get('exclude_files','').split(',')   if n.strip()}
        self.excl_types   = {t.strip().lower() for t in s.get('exclude_types','').split(',') if t.strip()}

        # TK Setup
        self.root = tk.Tk()
        self.root.title("Advanced File Selector")
        self.root.geometry("900x600")
        style = ttk.Style(self.root)
        style.configure("Treeview", font=('Segoe UI',12), rowheight=28)

        # Haupt-PanedWindow: Links Baum, Rechts Viewer
        paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Linke Seite: Filter + Tree + Controls
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        # Filter Eingabe
        fframe = ttk.Frame(left)
        ttk.Label(fframe, text="Filter Name:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        ent = ttk.Entry(fframe, textvariable=self.search_var)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ent.bind('<KeyRelease>', lambda e: self.refresh_tree())
        ttk.Button(fframe, text="✖", width=2,
                   command=lambda: (self.search_var.set(''), self.refresh_tree())
        ).pack(side=tk.LEFT)
        fframe.pack(fill=tk.X, pady=(0,5))

        # Treeview
        self.tree = ttk.Treeview(
            left,
            columns=('check','path'),
            show='tree',
            displaycolumns=('check',)
        )
        self.tree.column('check', width=30, anchor='center', stretch=False)
        self.tree.column('path', width=0, stretch=False)
        vsb = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscroll=vsb.set, selectmode='none')
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.check_states = {}

        # Kontextmenü für Ordner
        self.cm = tk.Menu(self.root, tearoff=0)
        self.cm.add_command(label="Markiere Ordner",    command=lambda: self._ctx_folder(True))
        self.cm.add_command(label="Entmarkiere Ordner", command=lambda: self._ctx_folder(False))
        self.tree.bind('<Button-3>', self._show_context_menu)
        self.tree.bind('<Button-1>', self._on_click_checkbox)

        # Auswahl-Buttons
        btnf = ttk.Frame(left)
        for txt, cmd in [
            ("Alle",   lambda: self._toggle_all(True)),
            ("Keine",  lambda: self._toggle_all(False)),
            ("Invert", self._toggle_invert),
            ("Exp All",self._expand_all),
            ("Col All",self._collapse_all)
        ]:
            ttk.Button(btnf, text=txt, command=cmd).pack(side=tk.LEFT, padx=3)
        btnf.pack(fill=tk.X, pady=(5,0))

        # Rechte Seite: Text-Viewer + Copy
        right = ttk.Frame(paned)
        paned.add(right, weight=2)
        topf = ttk.Frame(right)
        ttk.Label(topf, text="Export-Vorschau:").pack(side=tk.LEFT)
        ttk.Button(topf, text="Copy", command=self.copy_to_clipboard).pack(side=tk.RIGHT)
        topf.pack(fill=tk.X, pady=(0,5))

        self.text = tk.Text(right, wrap='word', font=('Consolas',11), state='disabled')
        tvsb = ttk.Scrollbar(right, orient='vertical', command=self.text.yview)
        self.text.configure(yscroll=tvsb.set)
        tvsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(fill=tk.BOTH, expand=True)

        # Export-Button
        ttk.Button(self.root, text="Exportieren → Vorschau", command=self.export_to_viewer).pack(pady=5)

        # Initialer Aufbau
        self.refresh_tree()

    def refresh_tree(self):
        # Clear
        for iid in self.tree.get_children(''):
            self.tree.delete(iid)
        self.check_states.clear()

        term = self.search_var.get().lower()
        # Sammle alle Dateien nach Config-Filtern
        valid = []
        for p in self.root_folder.rglob('*'):
            if p.is_dir(): continue
            if any(part in self.excl_folders for part in p.parts): continue
            if p.name in self.excl_files: continue
            ext = p.suffix.lower()
            if ext in self.excl_types: continue
            if term and term not in p.name.lower(): continue
            valid.append(p)

        # Baue echte Ordnerstruktur mit nur gültigen Dateien
        def add_nodes(parent, folder: Path):
            for item in sorted(folder.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.is_dir():
                    # Prüfe, ob dieser Ordner gültige Dateien enthält
                    if any(f in valid for f in item.rglob('*') if f.is_file()):
                        fid = self._insert_node(parent, item.name + '/', item)
                        add_nodes(fid, item)
                else:
                    if item in valid:
                        self._insert_node(parent, item.name, item)
        add_nodes('', self.root_folder)

    def _insert_node(self, parent, text, path: Path):
        iid = self.tree.insert(parent, tk.END, text=text, values=('☑', str(path)))
        self.check_states[iid] = True
        return iid

    def _on_click_checkbox(self, event):
        if self.tree.identify_region(event.x, event.y) == 'cell' and self.tree.identify_column(event.x) == '#1':
            iid = self.tree.identify_row(event.y)
            if iid:
                self._set_recursive(iid, not self.check_states.get(iid, False))

    def _set_recursive(self, iid, state):
        self.tree.set(iid, 'check', '☑' if state else '☐')
        self.check_states[iid] = state
        for c in self.tree.get_children(iid):
            self._set_recursive(c, state)

    def _toggle_all(self, state: bool):
        for iid in list(self.check_states):
            self._set_recursive(iid, state)

    def _toggle_invert(self):
        for iid, st in list(self.check_states.items()):
            self._set_recursive(iid, not st)

    def _expand_all(self):
        def recurse(i):
            self.tree.item(i, open=True)
            for c in self.tree.get_children(i): recurse(c)
        for i in self.tree.get_children(''): recurse(i)

    def _collapse_all(self):
        def recurse(i):
            self.tree.item(i, open=False)
            for c in self.tree.get_children(i): recurse(c)
        for i in self.tree.get_children(''): recurse(i)

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self._ctx_iid = iid
            self.cm.tk_popup(event.x_root, event.y_root)

    def _ctx_folder(self, mark: bool):
        self._set_recursive(self._ctx_iid, mark)

    def export_to_viewer(self):
        self.text.config(state='normal')
        self.text.delete('1.0', tk.END)
        for iid, ok in self.check_states.items():
            if not ok: continue
            p = Path(self.tree.set(iid, 'path'))
            if p.is_file():
                self.text.insert(tk.END, f"Pfad: {p.parent.as_posix()}\n")
                self.text.insert(tk.END, f"name: {p.name}\nINhalt:\n")
                try:
                    self.text.insert(tk.END, p.read_text(encoding='utf-8'))
                except Exception as e:
                    self.text.insert(tk.END, f"[Fehler: {e}]\n")
                self.text.insert(tk.END, "\n\n")
        self.text.config(state='disabled')

    def copy_to_clipboard(self):
        content = self.text.get('1.0', tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        messagebox.showinfo("Copied", "Vorschau wurde in die Zwischenablage kopiert.")

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    FileSelectorApp().run()
