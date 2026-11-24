"""Studio A: native, Unicode-safe components with a restrained comic treatment."""

import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont, ttk

COLORS = {
    "background": "#F7F3EB", "surface": "#FFFEFA", "text": "#25252D",
    "muted": "#66656F", "border": "#DAD4C9", "accent": "#3656D9",
    "hover": "#2944B4", "error": "#B42332", "success": "#18733D",
    "yellow": "#FFE18B", "selected": "#EDEBFF", "disabled": "#EAE5DC",
}
FONT = "Segoe UI"


def rounded(canvas, x, y, width, height, fill, outline, radius=12, thickness=1):
    r = min(radius, width / 2, height / 2)
    points = [x+r,y,x+width-r,y,x+width,y,x+width,y+r,
              x+width,y+height-r,x+width,y+height,x+width-r,y+height,
              x+r,y+height,x,y+height,x,y+height-r,x,y+r,x,y]
    return canvas.create_polygon(points, smooth=True, splinesteps=24,
                                 fill=fill, outline=outline, width=thickness)


class ComicButton(tk.Canvas):
    def __init__(self, parent, text, command, primary=False, width=150, **kwargs):
        self.label = text
        self.command = command
        self.primary = primary
        self.disabled = kwargs.pop("state", "normal") == "disabled"
        self.selected = False
        self.hovered = False
        self.focused = False
        super().__init__(parent, width=width, height=49 if primary else 42,
                         bg=parent.cget("background"), highlightthickness=0, takefocus=True,
                         cursor="hand2", **kwargs)
        self.bind("<Configure>", lambda _: self._draw())
        self.bind("<Enter>", lambda _: self._hover(True))
        self.bind("<Leave>", lambda _: self._hover(False))
        self.bind("<Button-1>", lambda _: self.invoke())
        self.bind("<Return>", lambda _: self.invoke())
        self.bind("<space>", lambda _: self.invoke())
        self.bind("<FocusIn>", lambda _: self._focus(True))
        self.bind("<FocusOut>", lambda _: self._focus(False))

    def _hover(self, value):
        self.hovered = value
        self._draw()

    def _focus(self, value):
        self.focused = value
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 5:
            return
        dark = self.primary or self.selected
        fill = COLORS["disabled"] if self.disabled else (
            COLORS["hover"] if self.primary and self.hovered else
            COLORS["accent"] if self.primary else COLORS["text"] if self.selected else
            COLORS["background"] if self.hovered else COLORS["surface"])
        color = COLORS["muted"] if self.disabled else "#FFFFFF" if dark else COLORS["text"]
        shadow = 4 if self.primary and not self.disabled else 0
        if shadow:
            rounded(self, 4, 4, w-5, h-5, COLORS["text"], COLORS["text"], 10)
        rounded(self, 1, 1, w-shadow-2, h-shadow-2, fill,
                COLORS["text"] if self.primary or self.focused or self.selected else COLORS["border"], 10,
                2 if self.focused else 1)
        self.create_text((w-shadow)/2, (h-shadow)/2, text=self.label,
                         font=(FONT, 10, "bold"), fill=color)
        self.configure(cursor="arrow" if self.disabled else "hand2")

    def configure(self, cnf=None, **kwargs):
        redraw = False
        if "text" in kwargs:
            self.label = kwargs.pop("text")
            redraw = True
        if "state" in kwargs:
            self.disabled = kwargs.pop("state") == "disabled"
            redraw = True
        result = super().configure(cnf, **kwargs) if cnf is not None or kwargs else None
        if redraw:
            self._draw()
        return result

    config = configure

    def state(self, states=None):
        if states:
            if "disabled" in states:
                self.disabled = True
            if "!disabled" in states:
                self.disabled = False
            self._draw()
        return ("disabled",) if self.disabled else ()

    def instate(self, states):
        return all(self.disabled if state == "disabled" else not self.disabled for state in states)

    def set_selected(self, selected):
        self.selected = selected
        self._draw()

    def invoke(self):
        if not self.disabled:
            self.focus_set()
            return self.command()


class ChoiceOption(ComicButton):
    """Compact radio option; label and circle share one keyboard/click target."""
    def __init__(self, parent, text, command, **kwargs):
        super().__init__(parent, text, command, **kwargs)
        self.configure(height=32)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 5:
            return
        if self.hovered and not self.disabled or self.focused:
            rounded(self,1,1,w-2,h-2,COLORS["background"],COLORS["border"] if self.focused else COLORS["background"],8)
        color = COLORS["muted"] if self.disabled else COLORS["accent"] if self.selected else COLORS["text"]
        self.create_oval(8,h/2-8,24,h/2+8,outline=color,width=1.5,
                         fill=COLORS["surface"])
        if self.selected:
            self.create_oval(12,h/2-4,20,h/2+4,fill=color,outline=color)
        self.create_text(34,h/2,text=self.label,anchor="w",font=(FONT,10),fill=color)
        self.configure(cursor="arrow" if self.disabled else "hand2")


class CompactSwitch(ComicButton):
    def __init__(self, parent, text, variable, **kwargs):
        self.variable = variable
        super().__init__(parent,text,self._toggle,**kwargs)
        self.configure(height=34)
        self.trace = variable.trace_add("write",lambda *_:self._draw())
        self.bind("<Destroy>",self._dispose,add="+")

    def _toggle(self):
        self.variable.set(not self.variable.get())

    def _dispose(self, event):
        if event.widget is self:
            self.variable.trace_remove("write",self.trace)

    def _draw(self):
        self.delete("all")
        w,h=self.winfo_width(),self.winfo_height()
        if w < 50:
            return
        on=self.variable.get()
        fill=COLORS["disabled"] if self.disabled else COLORS["accent"] if on else COLORS["muted"]
        rounded(self,w-45,h/2-11,44,22,fill,fill,11)
        x=w-23 if on else w-43
        self.create_oval(x,h/2-9,x+18,h/2+9,fill=COLORS["surface"],outline=COLORS["surface"])
        self.create_text(1,h/2,text=self.label,anchor="w",font=(FONT,10),
                         fill=COLORS["muted"] if self.disabled else COLORS["text"])
        if self.focused:
            self.create_rectangle(0,0,w-1,h-1,outline=COLORS["border"])
        self.configure(cursor="arrow" if self.disabled else "hand2")


class Panel(tk.Canvas):
    def __init__(self, parent, shadow=False, **kwargs):
        super().__init__(parent, bg=COLORS["background"], highlightthickness=0, **kwargs)
        self.content = tk.Frame(self, bg=COLORS["surface"])
        self.window = self.create_window(18, 18, window=self.content, anchor="nw")
        self.shadow = shadow
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        self.delete("border")
        offset = 4 if self.shadow else 0
        if self.shadow:
            rounded(self, 5, 5, event.width-7, event.height-7,
                    COLORS["text"], COLORS["text"])
            self.addtag_withtag("border", self.find_all()[-1])
        item = rounded(self, 1, 1, event.width-offset-3, event.height-offset-3,
                       COLORS["surface"], COLORS["text"] if self.shadow else COLORS["border"])
        self.addtag_withtag("border", item)
        self.tag_lower("border")
        self.itemconfigure(self.window, width=max(1,event.width-38-offset), height=max(1,event.height-38-offset))


def label(parent, text=None, variable=None, size=11, bold=False, muted=False, **kwargs):
    return tk.Label(parent, text=text, textvariable=variable, font=(FONT,size,"bold" if bold else "normal"),
                    bg=parent.cget("background"), fg=COLORS["muted"] if muted else COLORS["text"],
                    anchor="w", justify="left", **kwargs)


def configure_styles(app):
    global FONT
    available = set(tkfont.families(app))
    FONT = next((name for name in ("Segoe UI", "Arial", "Tahoma") if name in available), "TkDefaultFont")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name).configure(family=FONT, size=11)
    style = ttk.Style(app)
    style.theme_use("clam")
    style.configure(".", font=(FONT,11), background=COLORS["surface"], foreground=COLORS["text"])
    style.configure("TEntry", padding=10, fieldbackground=COLORS["background"], bordercolor=COLORS["border"])
    style.configure("TCheckbutton", background=COLORS["surface"], padding=(0,6))
    style.map("TCheckbutton", background=[("active",COLORS["surface"])])
    style.configure("Treeview", font=(FONT,10), rowheight=42, background=COLORS["surface"],
                    fieldbackground=COLORS["surface"], borderwidth=0)
    style.configure("Treeview.Heading", font=(FONT,10,"bold"), padding=(8,10), background=COLORS["background"])
    style.map("Treeview", background=[("selected",COLORS["selected"])], foreground=[("selected",COLORS["text"])])
    for name,color in [("Convert",COLORS["accent"]),("Done",COLORS["success"])]:
        style.configure(f"{name}.Horizontal.TProgressbar", background=color, troughcolor=COLORS["disabled"],
                        borderwidth=0, lightcolor=color, darkcolor=color, thickness=9)


def build_layout(app):
    app.geometry("1180x840")
    app.minsize(1000,760)
    body = tk.Frame(app, bg=COLORS["background"], padx=24, pady=20)
    body.pack(fill="both",expand=True)
    body.columnconfigure(1,weight=1)
    body.rowconfigure(2,weight=1)
    header = tk.Frame(body,bg=COLORS["background"])
    header.grid(row=0,column=0,columnspan=2,sticky="ew",pady=(0,18))
    logo = tk.Canvas(header,width=48,height=48,bg=COLORS["background"],highlightthickness=0)
    logo.pack(side="left",padx=(0,14))
    app.brand_image=tk.PhotoImage(file=str(Path(__file__).resolve().parent / "assets/brand-48.png"))
    logo.create_image(24,24,image=app.brand_image)
    brand=tk.Frame(header,bg=COLORS["background"]);brand.pack(side="left")
    label(brand,"MD Converter",size=19,bold=True).pack(anchor="w")
    label(brand,"Word · Excel · PDF · PowerPoint · Văn bản",size=10,muted=True).pack(anchor="w")
    tk.Label(header,text="  MARKDOWN  ",font=(FONT,10,"bold"),bg=COLORS["yellow"],fg=COLORS["text"],padx=10,pady=7).pack(side="right")
    intro=tk.Frame(body,bg=COLORS["background"])
    intro.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(0,20))
    label(intro,"Tài liệu vào. Markdown ra.",size=24,bold=True).pack(anchor="w")
    label(intro,"Chọn tài liệu, chuyển đổi và xem kết quả ngay tại đây.",size=11,muted=True).pack(anchor="w",pady=(4,0))

    settings=Panel(body,shadow=True,width=310)
    settings.grid(row=2,column=0,sticky="nsew",padx=(0,20))
    settings.grid_propagate(False)
    form=settings.content
    app.settings_panel=settings
    app.settings_form=form
    form.columnconfigure(0,weight=1)
    def heading(row,number,text):
        bar=tk.Frame(form,bg=COLORS["surface"]);bar.grid(row=row,column=0,sticky="ew",pady=(0,10))
        tk.Label(bar,text=number,font=(FONT,10,"bold"),bg=COLORS["yellow"],fg=COLORS["text"],padx=8,pady=3).pack(side="left",padx=(0,10))
        label(bar,text,size=12,bold=True).pack(side="left")
    heading(0,"1","Nguồn tài liệu")
    modes=tk.Frame(form,bg=COLORS["surface"])
    modes.grid(row=1,column=0,sticky="ew",pady=(0,8));modes.columnconfigure((0,1),weight=1)
    def mode(value):
        app.mode.set(value);app._change_mode()
    app.file_mode_button=ChoiceOption(modes,"Theo file",lambda:mode("files"),width=125)
    app.folder_mode_button=ChoiceOption(modes,"Theo folder",lambda:mode("folder"),width=125)
    app.file_mode_button.grid(row=0,column=0,sticky="ew",padx=(0,4))
    app.folder_mode_button.grid(row=0,column=1,sticky="ew",padx=(4,0))
    app.file_mode_button.set_selected(True)
    app.locked_controls.extend([app.file_mode_button,app.folder_mode_button])
    def button(parent,text,command,**kwargs):
        widget=ComicButton(parent,text,command,**kwargs);app.locked_controls.append(widget);return widget
    source_actions=tk.Frame(form,bg=COLORS["surface"])
    source_actions.grid(row=2,column=0,sticky="ew");source_actions.columnconfigure(0,weight=1)
    app.choose=button(source_actions,"Chọn tài liệu…",app._choose_source,width=180)
    app.choose.grid(row=0,column=0,sticky="ew",padx=(0,6))
    button(source_actions,"Xóa",app._clear,width=66).grid(row=0,column=1)
    app.source_display=ttk.Entry(form,textvariable=app.selection_note,font=(FONT,10),state="readonly",width=1)
    app.source_display.grid(row=3,column=0,sticky="ew",pady=(8,4))
    app.recursive_check=CompactSwitch(form,"Bao gồm thư mục con",variable=app.recursive)
    app.recursive_check.grid(row=4,column=0,sticky="ew")
    app.recursive_check.state(["disabled"]);app.locked_controls.append(app.recursive_check)
    ttk.Separator(form,orient="horizontal").grid(row=5,column=0,sticky="ew",pady=(14,12))
    heading(6,"2","Nơi lưu kết quả")
    label(form,"Đường dẫn lưu (có thể để trống)",size=10,muted=True).grid(row=7,column=0,sticky="w",pady=(0,6))
    output_row=tk.Frame(form,bg=COLORS["surface"])
    output_row.grid(row=8,column=0,sticky="ew");output_row.columnconfigure(0,weight=1)
    app.output_entry=ttk.Entry(output_row,textvariable=app.output_folder,font=(FONT,10),width=1)
    app.output_entry.grid(row=0,column=0,sticky="ew",padx=(0,6));app.locked_controls.append(app.output_entry)
    button(output_row,"Chọn…",app._choose_output,width=76).grid(row=0,column=1)
    reset=button(form,"Dùng nơi lưu tự động",app._use_auto_output)
    reset.configure(height=32)
    reset.grid(row=9,column=0,sticky="ew",pady=(6,8))
    app.output_hint_label=label(form,variable=app.output_hint,size=10,muted=True,height=3,wraplength=265)
    app.output_hint_label.grid(row=10,column=0,sticky="ew")
    form.rowconfigure(12,weight=1)
    app.settings_note=label(form,"DOC cũ: trích xuất văn bản.\nPDF scan cần OCR trước.",size=9,muted=True)
    app.settings_note.grid(row=13,column=0,sticky="sw",pady=(10,0))

    right=tk.Frame(body,bg=COLORS["background"])
    right.grid(row=2,column=1,sticky="nsew");right.columnconfigure(0,weight=1);right.rowconfigure(1,weight=1)
    toolbar=tk.Frame(right,bg=COLORS["background"])
    toolbar.grid(row=0,column=0,sticky="ew",pady=(0,10))
    app.list_toggle=ComicButton(toolbar,"Hiện danh sách (0)",app._toggle_list,width=190)
    app.list_toggle.pack(side="left")
    label(toolbar,variable=app.count_text,size=10,muted=True).pack(side="right")
    app.panes=ttk.Panedwindow(right,orient="horizontal")
    app.panes.grid(row=1,column=0,sticky="nsew")
    app.listing=Panel(app.panes,width=300)
    listing=app.listing.content;listing.columnconfigure(0,weight=1);listing.rowconfigure(1,weight=1)
    label(listing,"Danh sách tài liệu",size=12,bold=True).grid(row=0,column=0,sticky="w",pady=(0,12))
    app.tree=ttk.Treeview(listing,columns=("name","status"),show="headings",selectmode="browse")
    app.tree.heading("name",text="Tài liệu");app.tree.heading("status",text="Trạng thái")
    app.tree.column("name",width=180,minwidth=110);app.tree.column("status",width=105,minwidth=90,stretch=False)
    app.tree.grid(row=1,column=0,sticky="nsew")
    scroll=ttk.Scrollbar(listing,orient="vertical",command=app.tree.yview);scroll.grid(row=1,column=1,sticky="ns")
    horizontal=ttk.Scrollbar(listing,orient="horizontal",command=app.tree.xview);horizontal.grid(row=2,column=0,sticky="ew")
    app.tree.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set)
    app.tree.tag_configure("error",foreground=COLORS["error"]);app.tree.tag_configure("success",foreground=COLORS["success"])
    app.tree.bind("<<TreeviewSelect>>",app._show_selection)
    preview_panel=Panel(app.panes)
    preview=preview_panel.content;preview.columnconfigure(0,weight=1);preview.rowconfigure(1,weight=1)
    label(preview,variable=app.preview_title,size=12,bold=True).grid(row=0,column=0,sticky="w",pady=(0,14))
    app.preview=tk.Text(preview,wrap="word",font=(FONT,11),bg=COLORS["surface"],fg=COLORS["text"],
                        relief="flat",highlightthickness=0,padx=2,pady=4,spacing1=3,spacing3=5,width=20,height=4,state="disabled")
    app.preview.grid(row=1,column=0,sticky="nsew")
    scrollbar=ttk.Scrollbar(preview,orient="vertical",command=app.preview.yview);scrollbar.grid(row=1,column=1,sticky="ns")
    app.preview.configure(yscrollcommand=scrollbar.set)
    app.panes.add(preview_panel,weight=3)
    app._set_preview("Nội dung Markdown sẽ xuất hiện sau khi chuyển đổi.\n\nBạn có thể bật danh sách tài liệu để chọn file cần xem.")

    progress=tk.Frame(right,bg=COLORS["background"])
    progress.grid(row=2,column=0,sticky="ew",pady=(16,10));progress.columnconfigure(0,weight=1)
    app.status_label=label(progress,variable=app.status,size=10,bold=True,wraplength=510)
    app.status_label.grid(row=0,column=0,sticky="w")
    label(progress,variable=app.progress_text,size=13,bold=True).grid(row=0,column=1,sticky="e",padx=(12,0))
    app.progress=ttk.Progressbar(progress,maximum=100,style="Convert.Horizontal.TProgressbar")
    app.progress.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(10,0))
    actions=tk.Frame(right,bg=COLORS["background"]);actions.grid(row=3,column=0,sticky="ew")
    app.stop_button=ComicButton(actions,"Dừng",app._cancel,state="disabled",width=100)
    app.stop_button.pack(side="left")
    app.start_button=button(actions,"Bắt đầu chuyển đổi  →",app._start,primary=True,width=250)
    app.start_button.pack(side="right")
    footer=tk.Frame(right,bg=COLORS["background"]);footer.grid(row=4,column=0,sticky="ew",pady=(12,0));footer.columnconfigure(0,weight=1)
    app.link=label(footer,variable=app.link_text,size=9,muted=True,wraplength=470)
    app.link.grid(row=0,column=0,sticky="ew",padx=(0,10))
    app.link.bind("<Button-1>",lambda _:app._open_output());app.link.bind("<Return>",lambda _:app._open_output())
    app.open_button=ComicButton(footer,"Mở folder kết quả",app._open_output,state="disabled",width=175)
    app.open_button.grid(row=0,column=1,sticky="e")
    right.bind("<Configure>",lambda e: (
        app.status_label.configure(wraplength=max(180,e.width-75)),
        app.link.configure(wraplength=max(140,e.width-210))))
