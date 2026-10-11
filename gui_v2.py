"""运行 python gui_v2.py。仅使用 Python 标准库，Python 3.12+。"""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from test1 import build_plan, execute_plan, summarize


STATUS = {'Ready': '待整理', 'Success': '成功', 'Skipped': '跳过', 'Failed': '失败'}


class OrganizerApp:
    def __init__(self, root):
        self.root = root
        self.plan = None
        self.busy = False
        self.events = queue.Queue()
        self.folder = tk.StringVar()
        self.conflict = tk.StringVar(value='跳过同名文件')
        self.unknown = tk.BooleanVar(value=False)
        self.summary = tk.StringVar(value='选择文件夹，预览分类结果后开始整理')
        root.title('文件整理助手')
        # 留出标题栏和任务栏空间，避免初始窗口超出较小屏幕。
        width = min(1120, max(1, root.winfo_screenwidth() - 80))
        height = min(730, max(1, root.winfo_screenheight() - 120))
        root.geometry(f'{width}x{height}')
        root.minsize(min(760, width), min(480, height))
        root.configure(background='#F3F6FB')
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#F3F6FB')
        style.configure('TLabel', background='#F3F6FB', foreground='#243249')
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 24, 'bold'))
        style.configure('Hint.TLabel', foreground='#64748B')
        style.configure('TButton', padding=(16, 10))
        style.configure('Accent.TButton', background='#2563EB', foreground='white')
        style.map('Accent.TButton', background=[('disabled', '#A8B8D0'), ('active', '#1D4ED8')])
        style.configure('TCheckbutton', background='#F3F6FB')
        style.configure('Treeview', rowheight=34, background='white', fieldbackground='white', borderwidth=0)
        style.configure('Treeview.Heading', background='#E3EBF7', padding=10, font=('Microsoft YaHei UI', 10, 'bold'))
        style.map('Treeview', background=[('selected', '#DBEAFE')], foreground=[('selected', '#172554')])

        # 先为底部操作栏分配空间，极小窗口或高 DPI 时也优先显示按钮。
        footer = ttk.Frame(root, padding=(16, 0, 16, 16))
        footer.pack(side='bottom', fill='x')
        footer.columnconfigure(0, weight=1)
        main = ttk.Frame(root, padding=(16, 16, 16, 0))
        main.pack(fill='both', expand=True)
        main.columnconfigure(0, weight=1)
        # 只有表格所在行伸缩；底部进度条和按钮保留各自需要的高度。
        main.rowconfigure(6, weight=1)
        ttk.Label(main, text='文件整理助手', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(main, text='先预览，再整理。让散落的文件各归其位。', style='Hint.TLabel').grid(row=1, column=0, sticky='w', pady=(4, 12))
        location = ttk.Frame(main)
        location.grid(row=2, column=0, sticky='ew')
        self.path_entry = ttk.Entry(location, textvariable=self.folder)
        self.path_entry.pack(side='left', fill='x', expand=True, ipady=8)
        self.browse_button = ttk.Button(location, text='选择文件夹', command=self.browse)
        self.browse_button.pack(side='left', padx=(10, 0))
        options = ttk.Frame(main)
        options.grid(row=3, column=0, sticky='ew', pady=10)
        ttk.Label(options, text='同名处理').pack(side='left', padx=(0, 10))
        self.conflict_box = ttk.Combobox(options, textvariable=self.conflict, state='readonly',
                                        values=['跳过同名文件', '自动重命名'], width=18)
        self.conflict_box.pack(side='left')
        self.unknown_check = ttk.Checkbutton(options, text='未知类型和无扩展名文件归入 others', variable=self.unknown)
        self.unknown_check.pack(side='left', padx=18)
        ttk.Label(main, text='仅整理当前层；不进入子文件夹。分类按扩展名判断，不读取文件内容。', style='Hint.TLabel').grid(row=4, column=0, sticky='w')
        ttk.Label(main, textvariable=self.summary, font=('Microsoft YaHei UI', 11, 'bold')).grid(row=5, column=0, sticky='w', pady=10)
        table = ttk.Frame(main)
        table.grid(row=6, column=0, sticky='nsew')
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=('name', 'type', 'target', 'status', 'detail'), show='headings', height=1)
        for key, label, width in [('name', '文件名', 210), ('type', '类型', 85), ('target', '目标相对路径', 260), ('status', '状态', 85), ('detail', '说明', 260)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=70)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(table, orient='horizontal', command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        for tag, color in [('Ready', '#1D4ED8'), ('Success', '#15803D'), ('Skipped', '#946200'), ('Failed', '#B91C1C')]:
            self.tree.tag_configure(tag, foreground=color)
        self.tree.tag_configure('stripe', background='#F7F9FD')
        self.progress = ttk.Progressbar(footer, mode='determinate')
        self.progress.grid(row=0, column=0, sticky='ew', pady=(10, 8))
        actions = ttk.Frame(footer)
        actions.grid(row=1, column=0, sticky='ew')
        self.preview_button = ttk.Button(actions, text='预览整理', command=self.preview)
        self.preview_button.pack(side='left')
        self.organize_button = ttk.Button(actions, text='开始整理', style='Accent.TButton', command=self.organize, state='disabled')
        self.organize_button.pack(side='right')
        for variable in (self.folder, self.conflict, self.unknown):
            variable.trace_add('write', self.invalidate)
        root.after(80, self.poll)

    def invalidate(self, *_):
        self.plan = None
        self.organize_button.configure(state='disabled')
        self.tree.delete(*self.tree.get_children())
        self.summary.set('设置已更新，请重新预览')
        self.progress['value'] = 0

    def browse(self):
        folder = filedialog.askdirectory(parent=self.root)
        if folder:
            self.folder.set(folder)

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.path_entry, self.browse_button, self.unknown_check, self.preview_button):
            widget.configure(state='disabled' if busy else 'normal')
        self.conflict_box.configure(state='disabled' if busy else 'readonly')
        self.organize_button.configure(state='disabled')

    def start(self, job, mode):
        self.set_busy(True)
        self.progress['value'] = 0
        self.summary.set('正在扫描文件…' if mode == 'preview' else '正在整理，请等待…')
        if mode == 'preview':
            self.progress.configure(mode='indeterminate')
            self.progress.start(12)
        else:
            self.progress.configure(mode='determinate')
        def worker():
            try:
                self.events.put(('done', mode, job()))
            except Exception as error:
                self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=False).start()

    def preview(self):
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showwarning('提示', '请先选择文件夹', parent=self.root)
            return
        conflict = 'rename' if self.conflict.get() == '自动重命名' else 'skip'
        unknown = self.unknown.get()
        self.plan = None
        self.start(lambda: build_plan(folder, conflict, unknown), 'preview')

    def organize(self):
        if self.plan is None or self.busy:
            return
        plan = self.plan
        count = summarize(plan)['preview']
        if messagebox.askyesno('确认整理', f'将整理 {count} 个文件：\n{plan.folder}\n\n文件会移入分类目录；此版本不提供一键撤销。', parent=self.root):
            self.plan = None
            def progress(current, total):
                # 限制事件量，避免大量文件产生大量 UI 更新。
                if current % max(1, total // 100) == 0 or current == total:
                    self.events.put(('progress', current * 100 / max(total, 1)))
            self.start(lambda: execute_plan(plan, progress), 'execute')

    def render(self, plan, mode):
        self.tree.delete(*self.tree.get_children())
        entries = plan.entries
        def batch(start=0):
            for index in range(start, min(start + 250, len(entries))):
                entry = entries[index]
                target = str(entry.destination.relative_to(plan.folder)) if entry.destination else '—'
                self.tree.insert('', 'end', values=(entry.source.name, entry.kind or '无扩展名', target,
                                 STATUS[entry.status], entry.detail), tags=(entry.status, 'stripe' if index % 2 else ''))
            if start + 250 < len(entries):
                self.root.after(1, lambda: batch(start + 250))
            else:
                counts = summarize(plan)
                self.set_busy(False)
                self.summary.set(f"待整理 {counts['preview']}    成功 {counts['success']}    跳过 {counts['skip']}    失败 {counts['fail']}")
                self.plan = plan if mode == 'preview' else None
                if self.plan and counts['preview']:
                    self.organize_button.configure(state='normal')
        batch()

    def poll(self):
        for _ in range(150):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event[0] == 'progress':
                self.progress['value'] = event[1]
            elif event[0] == 'error':
                self.progress.stop()
                self.progress.configure(mode='determinate', value=0)
                self.set_busy(False)
                self.plan = None
                self.tree.delete(*self.tree.get_children())
                self.summary.set('操作失败，请检查文件夹后重试')
                messagebox.showerror('操作失败', event[1], parent=self.root)
            else:
                self.progress.stop()
                self.progress.configure(mode='determinate', value=100)
                self.render(event[2], event[1])
        self.root.after(80, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('正在处理', '请等待当前操作结束后关闭窗口。', parent=self.root)
        else:
            self.root.destroy()


if __name__ == '__main__':
    OrganizerApp(tk.Tk()).root.mainloop()
