"""Okno aplikacji (tkinter - wbudowane w Pythona, działa offline)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__, engine
from .detector import Finding, add_custom, build_pattern

ON = "☑"
OFF = "☐"


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".anonimizator")
    d = Path(base) / "AnonimizatorCV"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_error(exc: BaseException) -> Path:
    """Zapisuje szczegóły błędu do pliku (bez treści CV) i zwraca jego ścieżkę."""
    import platform
    import traceback
    from datetime import datetime
    path = log_dir() / "bledy.log"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} | wersja {__version__} | "
                f"{platform.platform()} | Python {platform.python_version()}\n")
        f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return path


def show_error(parent, title: str, exc: BaseException, friendly: str):
    path = log_error(exc)
    try:
        parent.clipboard_clear()
        parent.clipboard_append(open(path, encoding="utf-8").read()[-4000:])
    except Exception:
        pass
    messagebox.showerror(title, f"{friendly}\n\nSzczegóły: {exc}\n\nOpis błędu został zapisany w pliku:\n{path}\n"
                                "i skopiowany do schowka - można go wkleić w e-mailu lub wiadomości.",
                         parent=parent)


def _open_path(path: str):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class AreaDialog(tk.Toplevel):
    """Okno do zaznaczania myszką obszarów do zamazania (np. zdjęcia)."""

    MAX_W, MAX_H = 760, 860

    def __init__(self, parent, pages, areas):
        super().__init__(parent)
        from PIL import ImageTk
        self._ImageTk = ImageTk
        self.title("Zamaż obszar - zaznacz myszką prostokąt (np. zdjęcie)")
        self.transient(parent)
        self.pages = pages
        self.areas = list(areas)
        self.result = None
        self.i = 0
        self.start = None
        self.tmp = None

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        self.prev_b = ttk.Button(bar, text="◀ Poprzednia", command=lambda: self.show(self.i - 1))
        self.prev_b.pack(side="left")
        self.page_lbl = ttk.Label(bar, text="")
        self.page_lbl.pack(side="left", padx=8)
        self.next_b = ttk.Button(bar, text="Następna ▶", command=lambda: self.show(self.i + 1))
        self.next_b.pack(side="left")
        ttk.Button(bar, text="Cofnij ostatni", command=self.undo).pack(side="left", padx=(16, 4))
        ttk.Button(bar, text="Wyczyść stronę", command=self.clear).pack(side="left")
        ttk.Button(bar, text="Gotowe", command=self.ok).pack(side="right")

        self.canvas = tk.Canvas(self, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(padx=6, pady=(0, 6))
        self.canvas.bind("<ButtonPress-1>", self.down)
        self.canvas.bind("<B1-Motion>", self.move)
        self.canvas.bind("<ButtonRelease-1>", self.up)
        self.protocol("WM_DELETE_WINDOW", self.ok)
        self.show(0)
        self.grab_set()

    def show(self, i):
        if not 0 <= i < len(self.pages):
            return
        self.i = i
        img = self.pages[i]
        k = min(self.MAX_W / img.width, self.MAX_H / img.height, 1.5)
        self.w, self.h = round(img.width * k), round(img.height * k)
        self.photo = self._ImageTk.PhotoImage(img.resize((self.w, self.h)))
        self.canvas.config(width=self.w, height=self.h)
        self.page_lbl.config(text=f"Strona {i + 1} z {len(self.pages)}")
        self.prev_b.config(state="normal" if i > 0 else "disabled")
        self.next_b.config(state="normal" if i < len(self.pages) - 1 else "disabled")
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        c.create_image(0, 0, image=self.photo, anchor="nw")
        for p, x0, y0, x1, y1 in self.areas:
            if p == self.i:
                c.create_rectangle(x0 * self.w, y0 * self.h, x1 * self.w, y1 * self.h,
                                   fill="black", stipple="gray50", outline="red", width=2)

    def down(self, e):
        self.start = (e.x, e.y)
        self.tmp = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def move(self, e):
        if self.start:
            self.canvas.coords(self.tmp, *self.start, e.x, e.y)

    def up(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        self.start = None
        x0, x1 = sorted((max(0, min(x0, self.w)), max(0, min(e.x, self.w))))
        y0, y1 = sorted((max(0, min(y0, self.h)), max(0, min(e.y, self.h))))
        if x1 - x0 > 5 and y1 - y0 > 5:
            self.areas.append((self.i, x0 / self.w, y0 / self.h, x1 / self.w, y1 / self.h))
        self.redraw()

    def undo(self):
        for k in range(len(self.areas) - 1, -1, -1):
            if self.areas[k][0] == self.i:
                del self.areas[k]
                break
        self.redraw()

    def clear(self):
        self.areas = [a for a in self.areas if a[0] != self.i]
        self.redraw()

    def ok(self):
        self.result = self.areas
        self.grab_release()
        self.destroy()


class App(tk.Tk):
    def __init__(self, initial_file: str | None = None):
        super().__init__()
        self.title(f"Anonimizator CV {__version__}")
        self.geometry("1100x700")
        self.minsize(900, 560)
        self.path: str | None = None
        self.lines: list[str] = []
        self.findings: list[Finding] = []
        self.areas: list = []
        self.auto_areas: set = set()
        self.queue: list[str] = []   # tryb wielu plików
        self.qi = 0
        self.out_dir: Path | None = None
        self.batch_done: list = []
        self.busy = False
        self.blackout = tk.BooleanVar(value=False)
        self.remove_photos = tk.BooleanVar(value=True)
        self._build()
        if initial_file:
            self.after(100, lambda: self.load(initial_file))

    def report_callback_exception(self, exc, val, tb):
        show_error(self, "Nieoczekiwany błąd", val, "Coś poszło nie tak. Program dalej działa - "
                   "spróbuj jeszcze raz albo uruchom go ponownie.")

    # --- układ okna ----------------------------------------------------------
    def _build(self):
        style = ttk.Style(self)
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=8)
        style.configure("Treeview", rowheight=24)

        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")
        ttk.Button(top, text="Wybierz CV… (jedno lub kilka)", style="Big.TButton",
                   command=self.choose).pack(side="left")
        self.batch_bar = ttk.Frame(top)
        self.skip_btn = ttk.Button(self.batch_bar, text="Pomiń ten plik", command=self.skip)
        self.skip_btn.pack(side="left", padx=(0, 6))
        self.auto_btn = ttk.Button(self.batch_bar, text="Pozostałe zapisz automatycznie",
                                   command=self.auto_rest)
        self.auto_btn.pack(side="left")
        self.file_lbl = ttk.Label(top, text="Obsługiwane: PDF, Word (.docx), TXT, JPG, PNG",
                                  foreground="gray50")
        self.file_lbl.pack(side="left", padx=12)
        self.status_lbl = ttk.Label(top, text="", foreground="#0b5394", font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(side="right")

        self.warn_lbl = ttk.Label(self, text="", foreground="#b00020", wraplength=1000, padding=(12, 0))
        self.warn_lbl.pack(fill="x")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=12, pady=6)

        # lewa strona: znalezione dane
        left = ttk.Frame(paned)
        paned.add(left, weight=3)
        ttk.Label(left, text="Znalezione dane (kliknij ☑, aby włączyć/wyłączyć)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        cols = ("on", "kind", "text", "repl")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for c, t, w in zip(cols, ("", "Rodzaj", "Znaleziony tekst", "Zamiana na"), (34, 150, 260, 140)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, stretch=c in ("text",), anchor="center" if c == "on" else "w")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="top", fill="both", expand=True)
        sb.place(in_=self.tree, relx=1.0, rely=0, relheight=1.0, anchor="ne")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<space>", lambda e: self._toggle_selected())
        self.tree.bind("<Double-1>", lambda e: self._edit_replacement())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_selected())

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Zaznacz wszystko", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(btns, text="Odznacz wszystko", command=lambda: self._set_all(False)).pack(side="left", padx=4)
        ttk.Button(btns, text="Zmień zamianę…", command=self._edit_replacement).pack(side="left")

        add = ttk.LabelFrame(left, text="Coś zostało pominięte? Dopisz tekst do usunięcia", padding=6)
        add.pack(fill="x", pady=(8, 0))
        self.custom = ttk.Entry(add)
        self.custom.pack(side="left", fill="x", expand=True)
        self.custom.bind("<Return>", lambda e: self._add_custom())
        ttk.Button(add, text="Dodaj", command=self._add_custom).pack(side="left", padx=(6, 0))

        # prawa strona: podgląd
        right = ttk.Frame(paned)
        paned.add(right, weight=4)
        ttk.Label(right, text="Podgląd tekstu (żółte = zostanie usunięte; możesz zaznaczyć "
                              "tekst myszką i kliknąć „Usuń zaznaczone”)",
                  font=("Segoe UI", 10, "bold"), wraplength=520).pack(anchor="w")
        self.preview = tk.Text(right, wrap="word", font=("Segoe UI", 10), padx=8, pady=6,
                               background="#fbfbfb", foreground="#111111", insertbackground="#111111",
                               selectbackground="#9cc3ff", selectforeground="#000000",
                               relief="solid", borderwidth=1)
        psb = ttk.Scrollbar(right, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=psb.set)
        self.preview.pack(side="top", fill="both", expand=True)
        psb.place(in_=self.preview, relx=1.0, rely=0, relheight=1.0, anchor="ne")
        self.preview.tag_configure("hit", background="#ffe066", foreground="#000000")
        self.preview.tag_configure("sel_hit", background="#ff9f43", foreground="#000000")
        mod = 8 if sys.platform == "darwin" else 4  # Cmd na Macu, Ctrl na Windows
        self.preview.bind("<Key>", lambda e: None if e.state & mod else "break")  # tylko do odczytu
        ttk.Button(right, text="Usuń zaznaczone w podglądzie",
                   command=self._add_from_selection).pack(anchor="e", pady=(6, 0))

        # dół: opcje i zapis
        bottom = ttk.Frame(self, padding=(12, 6, 12, 12))
        bottom.pack(fill="x")
        opts = ttk.Frame(bottom)
        opts.pack(side="left")
        ttk.Radiobutton(opts, text="Zamień na etykiety (np. [KANDYDAT], [E-MAIL])",
                        variable=self.blackout, value=False).pack(anchor="w")
        ttk.Radiobutton(opts, text="Zamaż na czarno", variable=self.blackout, value=True).pack(anchor="w")
        ttk.Checkbutton(opts, text="Usuń zdjęcie kandydata", variable=self.remove_photos).pack(anchor="w")
        self.save_btn = ttk.Button(bottom, text="Zapisz zanonimizowane CV…", style="Big.TButton",
                                   command=self.save, state="disabled")
        self.save_btn.pack(side="right")
        self.area_btn = ttk.Button(bottom, text="Zamaż obszar… (np. zdjęcie)",
                                   command=self.choose_areas, state="disabled")
        self.area_btn.pack(side="right", padx=8)
        self.count_lbl = ttk.Label(bottom, text="", foreground="gray50")
        self.count_lbl.pack(side="right", padx=12)

    # --- wczytanie pliku -----------------------------------------------------
    FILETYPES = [("CV (PDF, Word, obrazki, TXT)",
                  "*.pdf *.docx *.txt *.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp"),
                 ("PDF", "*.pdf"), ("Word", "*.docx"),
                 ("Obrazki", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp"),
                 ("Tekst", "*.txt"), ("Wszystkie pliki", "*.*")]

    def choose(self):
        if self.busy:
            return
        paths = list(filedialog.askopenfilenames(title="Wybierz CV (możesz zaznaczyć kilka naraz)",
                                                 filetypes=self.FILETYPES))
        if not paths:
            return
        if len(paths) == 1:
            self.queue = []
            self.batch_bar.pack_forget()
            self.load(paths[0])
            return
        self.queue = sorted(paths, key=lambda p: Path(p).name.casefold())
        self.qi = 0
        self.batch_done = []
        self.out_dir = Path(self.queue[0]).parent / "CV zanonimizowane"
        self.out_dir.mkdir(exist_ok=True)
        self.batch_bar.pack(side="left", padx=12)
        messagebox.showinfo("Wiele plików", f"Wybrano {len(self.queue)} plików.\n\n"
                            "Każdy możesz przejrzeć i zapisać przyciskiem „Zapisz i dalej”, albo kliknąć "
                            "„Pozostałe zapisz automatycznie”.\n\nWyniki trafią do folderu:\n"
                            f"{self.out_dir}\n\nPliki dostaną numery (CV_01, CV_02…). Plik "
                            "lista_kandydatow.csv w tym folderze mówi, który numer to który oryginał - "
                            "nie wysyłaj go razem z CV.")
        self.load(self.queue[0])

    def _batch_name(self, src: str) -> Path:
        ext = Path(src).suffix.lower()
        n = 1
        while any(self.out_dir.glob(f"CV_{n:02d}.*")):
            n += 1
        return self.out_dir / f"CV_{n:02d}{ext}"

    def _record(self, src: str, out: Path, st: dict | None, note: str = ""):
        import csv
        from datetime import datetime
        lst = self.out_dir / "lista_kandydatow.csv"
        new = not lst.exists()
        with open(lst, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            if new:
                w.writerow(["plik zanonimizowany", "plik oryginalny", "data", "uwagi"])
            w.writerow([out.name if out else "", Path(src).name, f"{datetime.now():%Y-%m-%d %H:%M}", note])
        self.batch_done.append((src, out, st, note))

    def skip(self):
        if self.busy or not self.queue:
            return
        self._next()

    def _next(self):
        self.qi += 1
        if self.qi < len(self.queue):
            self.load(self.queue[self.qi])
        else:
            self._finish_batch()

    def _finish_batch(self):
        saved = [d for d in self.batch_done if d[1]]
        check = [d for d in self.batch_done if d[3]]
        msg = f"Gotowe. Zapisano {len(saved)} z {len(self.queue)} plików w folderze:\n{self.out_dir}"
        if check:
            msg += "\n\nSprawdź ręcznie:\n• " + "\n• ".join(
                f"{d[1].name if d[1] else Path(d[0]).name}: {d[3]}" for d in check[:12])
        self.queue = []
        self.batch_bar.pack_forget()
        if messagebox.askyesno("Wszystkie pliki", msg + "\n\nOtworzyć folder z wynikami?"):
            _open_path(str(self.out_dir))

    def auto_rest(self):
        if self.busy or not self.queue:
            return
        rest = self.queue[self.qi:]
        if not messagebox.askyesno("Zapisz automatycznie",
                                   f"Zapisać automatycznie {len(rest)} plik(ów), bez przeglądania?\n\n"
                                   "Program użyje tego, co sam wykryje. Pliki, w których coś może być nie tak, "
                                   "pokaże na końcu do sprawdzenia."):
            return
        blackout, photos = self.blackout.get(), self.remove_photos.get()
        out_names = {}

        def work():
            results = []
            for src in rest:
                out = self._batch_name(src)
                out.touch()  # rezerwacja numeru
                out_names[src] = out
                try:
                    _, findings = engine.analyze(src)
                    areas = engine.suggest_areas(src) if photos else []
                    st = engine.anonymize(src, str(out), findings, blackout=blackout,
                                          remove_photos=photos, manual=areas)
                    note = ""
                    if st.get("pozostalo"):
                        note = "w pliku mogło coś zostać"
                    elif not any(f.kind.startswith("Imię") for f in findings):
                        note = "nie wykryto imienia i nazwiska"
                    elif engine.supports_areas(src) and not areas and Path(src).suffix.lower() != ".pdf":
                        note = "nie wykryto zdjęcia - sprawdź"
                    results.append((src, out, st, note))
                except Exception as e:  # noqa: BLE001
                    log_error(e)
                    try:
                        out.unlink()
                    except OSError:
                        pass
                    results.append((src, None, None, f"błąd: {e}"))
            return results

        def done(results, error):
            if error is not None:
                show_error(self, "Błąd", error, "Przetwarzanie automatyczne zostało przerwane.")
                return
            for src, out, st, note in results:
                self._record(src, out, st, note)
            self.qi = len(self.queue)
            self._finish_batch()

        self._bg(f"Przetwarzanie {len(rest)} plików…", work, done)

    def _bg(self, message, work, done):
        """Uruchamia pracę w tle (OCR trwa kilka sekund), okno nie zamarza."""
        if self.busy:
            return
        self.busy = True
        self.status_lbl.config(text=message)
        self.config(cursor="watch")
        box = {}

        def run():
            try:
                box["result"] = work()
            except Exception as e:  # noqa: BLE001
                box["error"] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                self.after(100, poll)
                return
            self.busy = False
            self.status_lbl.config(text="")
            self.config(cursor="")
            done(box.get("result"), box.get("error"))

        self.after(100, poll)

    def load(self, path: str):
        def work():
            return engine.warnings_for(path), engine.analyze(path), engine.suggest_areas(path)

        def done(result, error):
            if isinstance(error, engine.UnsupportedFile):
                messagebox.showerror("Nieobsługiwany plik", str(error))
                return
            if error is not None:
                show_error(self, "Błąd", error, "Nie udało się odczytać pliku.")
                return
            warnings, (self.lines, self.findings), suggested = result
            self.path = path
            self.areas = list(suggested)
            self.auto_areas = set(suggested)
            if suggested:
                warnings.append("Wykryto prawdopodobne zdjęcie kandydata i zaznaczono je do zamazania. "
                                "Sprawdź to przyciskiem „Zamaż obszar…”.")
            label = Path(path).name
            if self.queue:
                label = f"Plik {self.qi + 1} z {len(self.queue)}: {label}"
            self.file_lbl.config(text=label, foreground="")
            self.save_btn.config(text="Zapisz i dalej ▶" if self.queue else "Zapisz zanonimizowane CV…")
            self.warn_lbl.config(text="\n".join(warnings))
            self.preview.delete("1.0", "end")
            self.preview.insert("1.0", "\n".join(self.lines))
            self.save_btn.config(state="normal")
            self.area_btn.config(state="normal" if engine.supports_areas(path) else "disabled")
            self._area_label()
            self._refresh()
            if not self.findings:
                messagebox.showinfo("Brak wyników", "Nie znaleziono danych osobowych. Sprawdź podgląd "
                                    "i w razie potrzeby dopisz tekst ręcznie.")

        self._bg("Odczytywanie pliku…" if not engine.supports_areas(path)
                 else "Odczytywanie (OCR może potrwać kilka sekund)…", work, done)

    def choose_areas(self):
        if not self.path:
            return
        try:
            pages = engine.render_pages(self.path)
        except Exception as e:
            show_error(self, "Błąd", e, "Nie udało się wyświetlić pliku.")
            return
        dlg = AreaDialog(self, pages, self.areas)
        self.wait_window(dlg)
        if dlg.result is not None:
            self.areas = dlg.result
            self.auto_areas = set()  # użytkownik obejrzał i zatwierdził
            self._area_label()

    def _area_label(self):
        n = len(self.areas)
        self.area_btn.config(text=f"Zamaż obszar… (zaznaczono: {n})" if n
                             else "Zamaż obszar… (np. zdjęcie)")

    # --- lista ---------------------------------------------------------------
    def _refresh(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i, f in enumerate(self.findings):
            self.tree.insert("", "end", iid=str(i),
                             values=(ON if f.enabled else OFF, f.kind, f.text, f.replacement))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        n = sum(f.enabled for f in self.findings)
        self.count_lbl.config(text=f"Do usunięcia: {n} z {len(self.findings)}")
        self._highlight()

    def _highlight(self):
        t = self.preview
        t.tag_remove("hit", "1.0", "end")
        text = t.get("1.0", "end-1c")
        for f in self.findings:
            if not f.enabled:
                continue
            for m in build_pattern(f).finditer(text):
                t.tag_add("hit", f"1.0+{m.start()}c", f"1.0+{m.end()}c")

    def _show_selected(self):
        t = self.preview
        t.tag_remove("sel_hit", "1.0", "end")
        sel = self.tree.selection()
        if not sel:
            return
        f = self.findings[int(sel[0])]
        text = t.get("1.0", "end-1c")
        first = None
        for m in build_pattern(f).finditer(text):
            t.tag_add("sel_hit", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
            first = first or f"1.0+{m.start()}c"
        if first:
            t.see(first)

    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            row = self.tree.identify_row(event.y)
            if row:
                f = self.findings[int(row)]
                f.enabled = not f.enabled
                self._refresh()
                return "break"

    def _toggle_selected(self):
        for row in self.tree.selection():
            f = self.findings[int(row)]
            f.enabled = not f.enabled
        self._refresh()

    def _set_all(self, value: bool):
        for f in self.findings:
            f.enabled = value
        self._refresh()

    def _edit_replacement(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Zmień zamianę", "Najpierw wybierz pozycję z listy.")
            return
        f = self.findings[int(sel[0])]
        new = simpledialog.askstring("Zmień zamianę", f"Na co zamienić „{f.text}”?\n"
                                     "(np. pseudonim „Kandydat A”; puste = usuń bez śladu)",
                                     initialvalue=f.replacement, parent=self)
        if new is not None:
            # ta sama zamiana dla wszystkich form tego samego kandydata
            for x in self.findings:
                if x is f or (x.kind == f.kind and x.replacement == f.replacement and f.kind.startswith("Imię")):
                    x.replacement = new
            self._refresh()

    def _save_batch(self):
        src = self.path
        out = self._batch_name(src)
        out.touch()
        blackout, photos, findings = self.blackout.get(), self.remove_photos.get(), self.findings
        areas = [a for a in self.areas if photos or a not in self.auto_areas]

        def work():
            return engine.anonymize(src, str(out), findings, blackout=blackout,
                                    remove_photos=photos, manual=areas)

        def done(st, error):
            if error is not None:
                try:
                    out.unlink()
                except OSError:
                    pass
                show_error(self, "Błąd zapisu", error, "Nie udało się zapisać pliku.")
                return
            note = "w pliku mogło coś zostać" if st.get("pozostalo") else ""
            self._record(src, out, st, note)
            self._next()

        self._bg("Zapisywanie…", work, done)

    def _add_custom(self, text: str | None = None):
        text = (text if text is not None else self.custom.get()).strip()
        if not text:
            return
        if add_custom(self.findings, text) is None:
            messagebox.showinfo("Dodaj", "Ten tekst jest już na liście.")
        self.custom.delete(0, "end")
        self._refresh()

    def _add_from_selection(self):
        try:
            txt = self.preview.get("sel.first", "sel.last")
        except tk.TclError:
            messagebox.showinfo("Usuń zaznaczone", "Zaznacz myszką fragment tekstu w podglądzie.")
            return
        for line in re.split(r"[\r\n]+", txt):
            if line.strip():
                self._add_custom(line)

    # --- zapis ---------------------------------------------------------------
    def save(self):
        if not self.path:
            return
        src = Path(self.path)
        if self.queue:
            return self._save_batch()
        out = filedialog.asksaveasfilename(
            title="Zapisz zanonimizowane CV", initialdir=str(src.parent),
            initialfile=engine.default_output_name(self.path), defaultextension=src.suffix.lower(),
            filetypes=[(engine.SUPPORTED.get(src.suffix.lower(), "Plik"), f"*{src.suffix.lower()}")])
        if not out:
            return
        blackout, photos, findings = self.blackout.get(), self.remove_photos.get(), self.findings
        # automatycznie wykryte zdjęcie zamazujemy tylko przy włączonej opcji "Usuń zdjęcie"
        areas = [a for a in self.areas if photos or a not in self.auto_areas]

        def work():
            return engine.anonymize(self.path, out, findings, blackout=blackout,
                                    remove_photos=photos, manual=areas)

        def done(st, error):
            if error is not None:
                show_error(self, "Błąd zapisu", error, "Nie udało się zapisać pliku. "
                           "Sprawdź, czy plik o tej nazwie nie jest otwarty w innym programie.")
                return
            msg = (f"Zapisano: {Path(out).name}\n\n"
                   f"Zamienionych fragmentów: {st['zamiany']}\n"
                   f"Usuniętych zdjęć / obszarów: {st['zdjecia']}\n"
                   f"Usuniętych linków: {st['linki']}\n"
                   "Wyczyszczono metadane (autor, tytuł).")
            if st.get("dodatkowo"):
                msg += ("\n\nPo ponownym odczytaniu wyniku usunięto dodatkowo:\n• "
                        + "\n• ".join(st["dodatkowo"][:8]))
            icon = "info"
            if st.get("pozostalo"):
                icon = "warning"
                msg += ("\n\nUWAGA: w pliku wynikowym nadal widać:\n• " + "\n• ".join(st["pozostalo"][:10]) +
                        "\nSprawdź plik ręcznie.")
            if messagebox.askyesno("Gotowe", msg + "\n\nOtworzyć plik, żeby go sprawdzić?", icon=icon):
                _open_path(out)

        self._bg("Zapisywanie…", work, done)


def selftest() -> int:
    """Sprawdza zbudowaną aplikację na przykładowych CV (używane przy budowaniu instalatora)."""
    import tempfile
    import traceback
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    log = Path(tempfile.gettempdir()) / "anonimizator_selftest.log"
    lines = []
    ok = True
    for name in ("przykladowe_CV.pdf", "przykladowe_CV.docx", "przykladowe_CV.jpg"):
        src = base / "przyklady" / name
        try:
            _, findings = engine.analyze(str(src))
            out = Path(tempfile.gettempdir()) / ("selftest_" + name)
            st = engine.anonymize(str(src), str(out), findings)
            good = len(findings) >= 8 and not st["pozostalo"] and st["zamiany"] > 0
            ok &= good
            lines.append(f"{name}: {'OK' if good else 'BLAD'} {st} znalezisk={len(findings)}")
        except Exception:
            ok = False
            lines.append(f"{name}: WYJATEK\n{traceback.format_exc()}")
    try:
        from . import ocr
        exe = ocr.tesseract_exe()
        lines.append(f"OCR: {ocr.backend()} | tesseract: {exe} | tessdata: {ocr.tessdata_dir()}")
        if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
            bundled = Path(sys.executable).resolve().parent / "tesseract" / "tesseract.exe"
            if not exe or Path(exe).resolve() != bundled.resolve() or not ocr.tessdata_dir():
                ok = False
                lines.append("BLAD: program nie używa dołączonego Tesseracta lub brak plików językowych")
    except Exception as e:
        ok = False
        lines.append(f"OCR: BLAD {e}")
    log.write_text("\n".join(lines), encoding="utf-8")
    return 0 if ok else 1


def main():
    if sys.platform.startswith("win"):
        try:  # ostre czcionki na ekranach z skalowaniem
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(selftest())
    initial = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        App(initial).mainloop()
    except Exception as e:  # błąd przy samym starcie
        path = log_error(e)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Anonimizator CV", f"Nie udało się uruchomić programu:\n{e}\n\n"
                                 f"Szczegóły zapisano w pliku:\n{path}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
