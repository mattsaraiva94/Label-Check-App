import tkinter as tk
from tkinter import ttk, messagebox
import csv
import time
import cv2
import logging
from pathlib import Path
from PIL import Image, ImageTk
import threading
import queue
import config
import main
import socket
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime
import gmes_check

class NewImageHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(('.jpg', '.png')):
            self.callback(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory and event.dest_path.lower().endswith(('.jpg', '.png')):
            self.callback(Path(event.dest_path))

class LabelCheckApp:
    def __init__(self, root):
        self.root = root
        root.title('Label Checker')
        root.geometry('1100x600')
        root.configure(bg='light gray')
        root.grid_columnconfigure(1, weight=1)
        root.grid_columnconfigure(2, weight=1)
        root.grid_rowconfigure(1, weight=1)
        self.stop_event = threading.Event()
        self.debug_mode = False
        root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.progress_queue = queue.Queue()
        self._build_ui()
        self._load_teaching_file()
        self.observer = None
        self._check_progress()
        self.last_summary = "Summary: Total Labels: 0 | Total fails: 0 | Fail rate: 0.0%"

    def _build_ui(self):
        # Label para mostrar SKU detectado
        self.sku_shown_var = tk.StringVar(value="SKU: -")
        self.sku_label = tk.Label(self.root, textvariable=self.sku_shown_var, bg='light gray',
                                  font=('Arial', 11, 'bold'))
        self.sku_label.grid(row=0, column=1, sticky='w', padx=5, pady=5)

        self.start_btn = tk.Button(self.root, text='START', state='normal', bg='blue', command=self.toggle_start)
        self.start_btn.grid(row=1, column=0, columnspan=1, pady=15, padx=15, sticky='w')

        # Botão DEBUG
        self.debug_btn = tk.Button(self.root, text='DEBUG', state='normal', bg='gray', command=self.toggle_debug)
        self.debug_btn.grid(row=1, column=1, columnspan=1, pady=15, sticky='w')

        tk.Label(self.root, text='Model Spec:', bg='light gray').grid(row=2, column=0, sticky='we', padx=5)
        self.spec_table = ttk.Treeview(self.root, columns=('Field', 'Value'), show='headings', height=5)
        self.spec_table.heading('Field', text='Field')
        self.spec_table.heading('Value', text='Value')
        self.spec_table.column('Field', width=100, anchor='w')
        self.spec_table.column('Value', width=200, anchor='w')
        self.spec_table.grid(row=2, column=1, sticky='nsew', padx=5, pady=2)
        self.default_fields = ['SKU', 'Basic Model', 'Capacity', 'Color', 'EAN']
        for fld in self.default_fields:
            self.spec_table.insert('', 'end', iid=fld, values=(fld, '-'))

        self.progress = ttk.Progressbar(self.root, mode='determinate')
        self.progress.grid(row=3, column=1, sticky='we', padx=5, pady=(2, 10))

        self.test_time_var = tk.StringVar(value="Test-time: 0.00s")
        tk.Label(self.root, textvariable=self.test_time_var, bg='light gray').grid(row=4, column=1, sticky='w', padx=5)

        self.summary_var = tk.StringVar(value="Summary: Total Labels: 0 | Total fails: 0 | Fail rate: 0.0%")
        self.summary_label = tk.Label(self.root, textvariable=self.summary_var, bg='light gray', font=('Arial', 11))
        self.summary_label.grid(row=5, column=1, sticky='w', padx=5, pady=(0, 10))

        tk.Label(self.root, text='Test Image:', bg='light gray').grid(row=0, column=2, sticky='w')
        self.canvas = tk.Canvas(self.root, width=600, height=500, bg='white')
        self.canvas.grid(row=1, column=2, rowspan=5, padx=10, pady=5, sticky='nsew')

    def _load_teaching_file(self):
        self.sku_data = {}
        try:
            with open(config.TEACHING_INI, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    sku = row['SKU'].strip()
                    self.sku_data[sku] = {k.strip(): v.strip() for k, v in row.items()}
        except Exception as e:
            messagebox.showerror("Error", f"Failed loading SKU list: {e}")

    def toggle_start(self):
        if self.start_btn['text'] == 'Start':
            self.start_btn.config(text='Stop', bg='yellow')
            self.stop_event.clear()
            handler = NewImageHandler(self._on_new_image)
            self.observer = Observer()
            self.observer.schedule(handler, str(config.WATCH_FOLDER), recursive=False)
            self.observer.start()

            # Busca SKU automático via log G-MES
            user_ip = self.get_ip_address()
            gmes_log_path = gmes_check.find_latest_gmes_log(ip=user_ip)
            sku_found = gmes_check.extract_last_sku_from_log(gmes_log_path) if gmes_log_path else None

            if not sku_found:
                self.root.after(0, lambda: messagebox.showwarning("Atenção",
                                                                  "Não foi possível identificar SKU pelo G-MES."))
                return

            self.sku_shown_var.set(f"SKU: {sku_found}")

            self.sku_info = self.sku_data.get(sku_found)
            if not self.sku_info:
                self.root.after(0, lambda: messagebox.showerror("Erro",
                                                                f"SKU '{sku_found}' não encontrado no SKU List.ini"))
                return

            # Atualiza tabela com info do SKU
            for fld in self.default_fields:
                self.spec_table.item(fld, values=(fld, self.sku_info.get(fld, '-')))
        else:
            self._stop()

    def _stop(self):
        self.start_btn.config(text='Start', bg='blue')
        self.stop_event.set()
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        self.canvas.delete('all')
        for fld in self.default_fields:
            self.spec_table.item(fld, values=(fld, '-'))
        self.progress.stop()
        self.progress['value'] = 0
        self.test_time_var.set("Test-time: 0.00s")
        self.summary_var.set("Summary: Total Labels: 0 | Total fails: 0 | Fail rate: 0.0%")
        self.summary_label.config(fg='black', bg='light gray')
        self.sku_shown_var.set("SKU: -")

    def toggle_debug(self):
        if self.debug_btn['text'] == 'DEBUG':
            # Exibe form para senha
            self.show_password_popup()
        elif 'STOP' in self.debug_btn['text']:
            self.debug_mode = False
            self.debug_btn.config(text='DEBUG', bg='gray')
            messagebox.showinfo("Debug", "Modo debug desativado.")

    def show_password_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Password")
        popup.geometry("250x100+600+350")
        popup.transient(self.root)
        popup.grab_set()
        tk.Label(popup, text="Enter Password:").pack(pady=5)
        entry = tk.Entry(popup, show="*")
        entry.pack(pady=5)
        entry.focus_set()

        def check_password():
            pwd = entry.get()
            if pwd == "Seda2025":
                self.debug_mode = True
                self.debug_btn.config(text="STOP DEBUG", bg="yellow")
                popup.destroy()
                messagebox.showinfo("Debug", "Modo debug ativado.\nAuto-aprendizado habilitado!")
            else:
                popup.destroy()

        btn = tk.Button(popup, text="OK", command=check_password)
        btn.pack(pady=5)
        popup.bind('<Return>', lambda e: check_password())

    def _on_close(self):
        self._stop()
        self.root.destroy()

    def _check_progress(self):
        try:
            while True:
                value = self.progress_queue.get_nowait()
                self.progress['value'] = value
        except queue.Empty:
            pass
        self.root.after(50, self._check_progress)

    def _on_new_image(self, path):
        def task():
            import time
            import cv2
            self.progress['value'] = 0

            # Só processa se o nome da imagem tiver 'img_code'
            if 'img_code' not in str(path).lower():
                print(f"Ignorado: {path.name}")
                return

            self.progress.start(10)
            img0 = None
            for _ in range(10):
                if self.stop_event.is_set():
                    return
                try:
                    img0 = cv2.imread(str(path))
                    if img0 is not None:
                        break
                except PermissionError:
                    time.sleep(0.2)

            quick_count = 0
            if img0 is not None:
                try:
                    quick_count = len(main.yolo1.predict(img0)[0].boxes)
                except Exception as e:
                    logging.error(f"Quick count prediction failed: {e}")
                    quick_count = 20  # fallback

            self.root.after(0, lambda: self.progress.config(maximum=100))
            start = time.time()

            # Quick annotation inicial
            try:
                img_q = cv2.imread(str(path))
                if img_q is None:
                    raise ValueError("Failed to load image for quick annotation")
                res_q = main.yolo1.predict(img_q)[0]
                ann_q = img_q.copy()
                for idx_q, box_q in enumerate(res_q.boxes):
                    x1, y1, x2, y2 = map(int, box_q.xyxy[0])
                    cv2.rectangle(ann_q, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    cv2.putText(ann_q, f"{idx_q + 1:02d}", (x1 + 5, y2 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                rgb_q = cv2.cvtColor(ann_q, cv2.COLOR_BGR2RGB)
                pil_q = Image.fromarray(rgb_q).resize((600, 500), resample=Image.LANCZOS)
                photo_q = ImageTk.PhotoImage(pil_q)
                self.root.after(0, lambda: [
                    self.canvas.delete('all'),
                    self.canvas.create_image(0, 0, anchor='nw', image=photo_q),
                    setattr(self.canvas, 'image', photo_q)
                ])
            except Exception:
                logging.exception("Label task exception during quick annotation")

            # Callback para atualizar canvas a cada label processada
            def gui_update_fn(annot_img):
                rgb = cv2.cvtColor(annot_img, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb).resize((600, 500), resample=Image.LANCZOS)
                photo = ImageTk.PhotoImage(pil)
                self.root.after(0, lambda: [
                    self.canvas.delete('all'),
                    self.canvas.create_image(0, 0, anchor='nw', image=photo),
                    setattr(self.canvas, 'image', photo)
                ])

            # Progresso proporcional a labels processadas
            def step_cb(current_idx, total_labels):
                pct = int((current_idx / total_labels) * 100)
                self.progress_queue.put(pct)

            try:
                annotated, count, ng_labels, all_label_results = main.process_image_pipeline(
                    str(path),
                    self.sku_info,
                    progress_callback=step_cb,
                    stop_event=self.stop_event,
                    gui_update_fn=gui_update_fn,
                    user_ip=self.get_ip_address()
                )
            except Exception as e:
                logging.exception("Label task exception in full pipeline")
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
                return

            # Mostra popups NG/OK para autoaprendizagem somente se debug_mode ativo
            if self.debug_mode:
                for ng in ng_labels:
                    self.show_label_ng_popup(ng["crop_img"], ng["logs"], ng["sku"], ng["label_num"])

            rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb).resize((600, 500), resample=Image.LANCZOS)
            photo = ImageTk.PhotoImage(pil)
            elapsed = time.time() - start

            def update():
                self.canvas.delete('all')
                self.canvas.create_image(0, 0, anchor='nw', image=photo)
                self.canvas.image = photo
                self.test_time_var.set(f"Test-time: {elapsed:.2f}s")
                # Cálculo do resumo
                total_labels = count
                total_fails = 0
                n_fields = 0
                for logs in all_label_results:
                    total_fails += sum(1 for v in logs.values() if not getattr(v, 'valid', False))
                    n_fields = max(n_fields, len(logs))
                fail_rate = 100 * total_fails / (total_labels * n_fields) if total_labels and n_fields else 0.0
                self.summary_var.set(
                    f"Summary: Total Labels: {total_labels} | Total fails: {total_fails} | Fail rate: {fail_rate:.1f}%")
                self.summary_label.config(fg='red' if fail_rate >= 90 else 'blue')
                self.progress['value'] = 100

            self.root.after(0, update)
            self.progress.stop()
            self.progress['value'] = 100

        threading.Thread(target=task, daemon=True).start()

    def show_label_ng_popup(self, crop_img, logs, sku, label_num):
        win = tk.Toplevel()
        win.title(f"Label NG - #{label_num}")
        win.geometry("420x340+600+300")
        lbl = tk.Label(win, text=f"Label #{label_num} NG - SKU: {sku}", font=('Arial', 14, 'bold'))
        lbl.pack()
        # Rotaciona 90 graus para visualização correta
        crop_img_rot = cv2.rotate(crop_img, cv2.ROTATE_90_CLOCKWISE)
        img = Image.fromarray(crop_img_rot[..., ::-1])  # BGR->RGB for PIL
        img = img.resize((400, 200))
        tkimg = ImageTk.PhotoImage(img)
        panel = tk.Label(win, image=tkimg)
        panel.image = tkimg
        panel.pack()
        # Texto NG
        info = "\n".join(
            [f"{k}: {getattr(v, 'ocr_pos', '')}" for k, v in logs.items() if not getattr(v, 'valid', False)])
        txt = tk.Label(win, text=f"Campos NG:\n{info}", fg="red")
        txt.pack()

        # Botão OK (adiciona variante)
        def approve():
            for k, v in logs.items():
                if not getattr(v, 'valid', False) and getattr(v, 'ocr_pos', '-') and v.ocr_pos != "-":
                    main.add_variant(sku, k, v.ocr_pos)
            win.destroy()

        btn_ok = tk.Button(win, text="OK (Adicionar variante)", command=approve, fg="green")
        btn_ok.pack(side='left', padx=10)

        # Botão NG (log NG)
        def reject():
            logs_dir = Path("logs") / "ng_labels"
            logs_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now()
            filename = f"Label #{label_num:02d}_{now.day:02d}:{now.hour:02d}:{now.minute:02d}.jpg"
            out_path = logs_dir / filename
            cv2.imwrite(str(out_path), crop_img_rot)
            win.destroy()

        btn_ng = tk.Button(win, text="NG (Salvar imagem)", command=reject, fg="red")
        btn_ng.pack(side='right', padx=10)

    def get_ip_address(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

if __name__ == '__main__':
    root = tk.Tk()
    app = LabelCheckApp(root)
    root.mainloop()
