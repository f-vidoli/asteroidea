from __future__ import annotations

import asyncio
import json
from typing import Any

from kivy.graphics import Color, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput

FONT = "AppMono"
BG = (0x14 / 255, 0x14 / 255, 0x10 / 255, 1)
PRIMARY = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 1)
MUTED = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 0.6)
DIM = (0xF7 / 255, 0xD1 / 255, 0x42 / 255, 0.25)


def _outline(widget, color=PRIMARY):
    with widget.canvas.after:
        widget._oline_c = Color(*color)
        widget._oline = Line(rectangle=(widget.x, widget.y, widget.width, widget.height), width=1)
    widget.bind(
        pos=lambda inst, *_: setattr(inst._oline, "rectangle", (inst.x, inst.y, inst.width, inst.height)),
        size=lambda inst, *_: setattr(inst._oline, "rectangle", (inst.x, inst.y, inst.width, inst.height)),
    )
    return widget


class BoolToggle(Button):
    def __init__(self, active: bool = False, **kwargs: Any) -> None:
        super().__init__(
            text="ON" if active else "OFF",
            size_hint=(None, None),
            size=("72dp", "32dp"),
            background_normal="",
            background_down="",
            font_name=FONT,
            bold=True,
            **kwargs,
        )
        self._active = bool(active)
        _outline(self, PRIMARY)
        self.bind(on_release=self._toggle)
        self._sync_style()

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = bool(value)
        self._sync_style()

    def _toggle(self, *_a: Any) -> None:
        self._active = not self._active
        self._sync_style()

    def _sync_style(self) -> None:
        self.text = "ON" if self._active else "OFF"
        self.background_color = PRIMARY if self._active else BG
        self.color = BG if self._active else PRIMARY


class PluginSettingsScreen(BoxLayout):
    """Screen listing installed plugins and editing parameters from plugin.json."""

    screen_name = "settings"

    def __init__(self, plugin_manager: Any, **kwargs: Any) -> None:
        super().__init__(orientation="vertical", spacing=0, **kwargs)
        self.plugin_manager = plugin_manager
        self._inputs: dict[str, dict[str, tuple[dict[str, Any], Any]]] = {}
        self.install_status: Label | None = None
        self.zip_input: TextInput | None = None
        self.repo_input: TextInput | None = None
        self.ref_input: TextInput | None = None

        self.scroll = ScrollView(do_scroll_x=False, bar_width="6dp", scroll_type=["bars", "content"])
        self.list_layout = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing="16dp",
            padding=["16dp", "18dp", "16dp", "24dp"],
        )
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        self.scroll.add_widget(self.list_layout)
        self.add_widget(self.scroll)

    def refresh(self) -> None:
        self.list_layout.clear_widgets()
        self._inputs.clear()
        self.list_layout.add_widget(self._build_install_card())

        manifests = self.plugin_manager.list_plugin_manifests()
        try:
            known = self.plugin_manager.widget_registry.list_types()
        except Exception:
            known = []
        dbg = Label(
            text=f"[debug] plugins={len(manifests)} widgets={len(known)}",
            size_hint_y=None,
            height="24dp",
            halign="left",
            valign="middle",
            color=DIM,
            font_name=FONT,
            font_size="11sp",
        )
        dbg.bind(size=lambda inst, _v: setattr(inst, "text_size", (inst.width, inst.height)))
        self.list_layout.add_widget(dbg)
        if not manifests:
            self.list_layout.add_widget(
                Label(
                    text="No installed plugins found.",
                    size_hint_y=None,
                    height="40dp",
                    color=MUTED,
                    font_name=FONT,
                )
            )
            return
        for manifest in manifests:
            self.list_layout.add_widget(self._build_plugin_card(manifest))

    def _base_card(self) -> BoxLayout:
        card = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=["16dp", "16dp", "16dp", "16dp"],
            spacing="10dp",
        )
        with card.canvas.before:
            Color(*BG)
            card._bg = Rectangle(pos=card.pos, size=card.size)
        card.bind(
            pos=lambda *_: (setattr(card._bg, "pos", card.pos), setattr(card._bg, "size", card.size)),
            size=lambda *_: (setattr(card._bg, "pos", card.pos), setattr(card._bg, "size", card.size)),
        )
        _outline(card, PRIMARY)
        return card

    def _build_install_card(self) -> BoxLayout:
        card = self._base_card()
        title = Label(
            text="[b]PLUGIN MANAGER[/b]",
            markup=True,
            size_hint_y=None,
            height="26dp",
            halign="left",
            valign="middle",
            color=PRIMARY,
            font_name=FONT,
        )
        title.bind(size=lambda inst, _v: setattr(inst, "text_size", (inst.width, None)))
        card.add_widget(title)

        hint = Label(
            text="Install/load plugins: local zip path or GitHub owner/repo. Installed plugins auto-load on next start.",
            size_hint_y=None,
            halign="left",
            valign="top",
            color=MUTED,
            font_name=FONT,
        )
        hint.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None)),
            texture_size=lambda inst, s: setattr(inst, "height", max(20, s[1])),
        )
        card.add_widget(hint)

        def mk_input(text: str = "", hint_text: str = "") -> TextInput:
            ti = TextInput(
                text=text,
                hint_text=hint_text,
                multiline=False,
                size_hint_y=None,
                height="36dp",
                background_normal="",
                background_active="",
                background_color=BG,
                foreground_color=PRIMARY,
                cursor_color=PRIMARY,
                hint_text_color=MUTED,
                padding=["10dp", "8dp"],
                font_name=FONT,
            )
            _outline(ti, MUTED)
            return ti

        self.zip_input = mk_input("", "/path/to/plugin.zip")
        card.add_widget(self._labeled_row("Local zip path", self.zip_input))

        self.repo_input = mk_input("", "owner/repo or https://github.com/owner/repo")
        card.add_widget(self._labeled_row("GitHub repo", self.repo_input))
        self.ref_input = mk_input("main", "branch/ref")
        card.add_widget(self._labeled_row("Ref", self.ref_input))

        actions = BoxLayout(size_hint_y=None, height="40dp", spacing="8dp")
        b_zip = self._small_btn("Install Zip")
        b_zip.size_hint_x = 1
        b_zip.width = 0
        b_zip.bind(on_release=lambda *_: self._run_async(self._do_install_zip()))
        b_gh = self._small_btn("Install GitHub")
        b_gh.size_hint_x = 1
        b_gh.width = 0
        b_gh.bind(on_release=lambda *_: self._run_async(self._do_install_github()))
        b_refresh = self._small_btn("Refresh")
        b_refresh.size_hint_x = 1
        b_refresh.width = 0
        b_refresh.bind(on_release=lambda *_: self.refresh())
        actions.add_widget(b_zip)
        actions.add_widget(b_gh)
        actions.add_widget(b_refresh)
        card.add_widget(actions)

        self.install_status = Label(
            text="",
            size_hint_y=None,
            height="22dp",
            halign="left",
            valign="middle",
            color=PRIMARY,
            font_name=FONT,
        )
        self.install_status.bind(size=lambda inst, _v: setattr(inst, "text_size", (inst.width, inst.height)))
        card.add_widget(self.install_status)

        self._recalc_card(card)
        return card

    def _labeled_row(self, label: str, widget: Any) -> BoxLayout:
        col = BoxLayout(orientation="vertical", spacing="4dp")
        lbl = Label(
            text=label,
            size_hint_y=None,
            height="18dp",
            halign="left",
            valign="middle",
            color=MUTED,
            font_name=FONT,
        )
        lbl.bind(size=lambda inst, _v: setattr(inst, "text_size", (inst.width, inst.height)))
        col.add_widget(lbl)
        col.add_widget(widget)
        return col

    def _small_btn(self, text: str, solid: bool = False) -> Button:
        b = Button(
            text=text,
            size_hint=(None, None),
            size=("110dp", "36dp"),
            background_normal="",
            background_down="",
            background_color=PRIMARY if solid else BG,
            color=BG if solid else PRIMARY,
            bold=True,
            font_name=FONT,
        )
        _outline(b, PRIMARY)
        return b

    def _set_status(self, msg: str, error: bool = False) -> None:
        if self.install_status:
            self.install_status.text = msg
            self.install_status.color = PRIMARY if not error else (1, 0.45, 0.35, 1)

    def _run_async(self, coro) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            asyncio.run(coro)

    async def _do_install_zip(self) -> None:
        path = (self.zip_input.text or "").strip() if self.zip_input else ""
        if not path:
            self._set_status("Enter a zip path.", True)
            return
        self._set_status("Installing from zip...")
        dest = await self.plugin_manager.install_from_zip(path, load=True)
        if dest:
            self._set_status(f"Installed and loaded: {dest.name}")
            self.refresh()
        else:
            self._set_status("Install failed. Check path/manifest/logs.", True)

    async def _do_install_github(self) -> None:
        repo = (self.repo_input.text or "").strip() if self.repo_input else ""
        ref = (self.ref_input.text or "main").strip() if self.ref_input else "main"
        if not repo:
            self._set_status("Enter a GitHub repo.", True)
            return
        self._set_status(f"Installing {repo}@{ref}...")
        dest = await self.plugin_manager.install_from_github(repo, ref=ref, load=True)
        if dest:
            self._set_status(f"Installed and loaded: {dest.name}")
            self.refresh()
        else:
            self._set_status("GitHub install failed. Check repo/ref/network.", True)

    def _confirm_remove(self, plugin_id: str, name: str) -> None:
        content = BoxLayout(orientation="vertical", spacing="10dp", padding="12dp")
        with content.canvas.before:
            Color(*BG)
            content._bg = Rectangle(pos=content.pos, size=content.size)
        content.bind(pos=lambda *_: setattr(content._bg, "pos", content.pos),
                     size=lambda *_: setattr(content._bg, "size", content.size))
        msg = Label(
            text=f"Remove plugin '{name}'?\n({plugin_id})\nThis will delete its files, settings, and memory.",
            halign="center",
            valign="middle",
            color=PRIMARY,
            font_name=FONT,
        )
        msg.bind(size=lambda inst, _v: setattr(inst, "text_size", (inst.width, inst.height)))
        content.add_widget(msg)

        btns = BoxLayout(size_hint_y=None, height="40dp", spacing="8dp")
        btns.add_widget(BoxLayout())
        cancel_btn = self._small_btn("Cancel")
        confirm_btn = self._small_btn("Remove")
        btns.add_widget(cancel_btn)
        btns.add_widget(confirm_btn)
        content.add_widget(btns)

        popup = Popup(
            title="Confirm removal",
            content=content,
            size_hint=(0.9, None),
            height="220dp",
            auto_dismiss=False,
            separator_color=PRIMARY,
            title_color=PRIMARY,
            background="",
            background_color=BG,
        )
        _outline(content, PRIMARY)
        cancel_btn.bind(on_release=lambda *_: popup.dismiss())
        confirm_btn.bind(on_release=lambda *_: (popup.dismiss(), self._run_async(self._do_remove(plugin_id))))
        popup.open()

    async def _do_remove(self, plugin_id: str) -> None:
        ok = await self.plugin_manager.remove_plugin(plugin_id)
        self._set_status(f"Removed {plugin_id}" if ok else f"Failed to remove {plugin_id}", not ok)
        self.refresh()

    async def _do_reload(self, plugin_id: str) -> None:
        ok = await self.plugin_manager.reload_plugin(plugin_id)
        self._set_status(f"Reloaded {plugin_id}" if ok else f"Failed to reload {plugin_id}", not ok)
        self.refresh()

    def _build_plugin_card(self, manifest: Any) -> BoxLayout:
        card = self._base_card()

        title = Label(
            text=f"[b]{manifest.name}[/b]  [color=#f7d14299]({manifest.plugin_id} v{manifest.version})[/color]",
            markup=True,
            size_hint_y=None,
            height="26dp",
            halign="left",
            valign="middle",
            color=PRIMARY,
            font_name=FONT,
        )
        title.bind(size=lambda inst, _v: setattr(inst, "text_size", (inst.width, None)))
        card.add_widget(title)

        if manifest.description:
            desc = Label(
                text=manifest.description,
                size_hint_y=None,
                halign="left",
                valign="top",
                color=MUTED,
                font_name=FONT,
            )
            desc.bind(
                width=lambda inst, w: setattr(inst, "text_size", (w, None)),
                texture_size=lambda inst, s: setattr(inst, "height", max(20, s[1])),
            )
            card.add_widget(desc)

        params = manifest.settings or []
        current = self.plugin_manager.get_plugin_settings(manifest.plugin_id)
        self._inputs[manifest.plugin_id] = {}

        custom_widget_type = None
        try:
            mf_path = manifest.path / "plugin.json" if manifest.path else None
            if mf_path and mf_path.exists():
                raw = json.loads(mf_path.read_text(encoding="utf-8"))
                custom_widget_type = raw.get("settings_widget")
        except Exception:
            custom_widget_type = None

        custom_widget = None
        if custom_widget_type:
            try:
                reg = self.plugin_manager.widget_registry
                print(f"[PluginSettings] creating custom settings widget '{custom_widget_type}' for {manifest.plugin_id}, known={reg.list_types()}")
                custom_widget = reg.create(
                    str(custom_widget_type),
                    {"plugin_id": manifest.plugin_id, "manifest": manifest, "plugin_manager": self.plugin_manager},
                )
            except Exception as exc:
                import traceback
                print(f"[PluginSettings] failed custom settings widget {custom_widget_type} for {manifest.plugin_id}: {exc}")
                traceback.print_exc()
                custom_widget = Label(
                    text=f"Failed to load custom settings widget: {custom_widget_type} ({exc})",
                    size_hint_y=None,
                    height="40dp",
                    color=PRIMARY,
                    font_name=FONT,
                )

        if custom_widget is not None:
            if getattr(custom_widget, "size_hint_y", None) in (1, None):
                custom_widget.size_hint_y = None
            if not getattr(custom_widget, "height", None) or custom_widget.height < 10:
                custom_widget.height = "120dp"
            card.add_widget(custom_widget)

        if not custom_widget and params:
            for param in params:
                row, widget = self._build_param_row(param, current.get(str(param.get("key"))))
                self._inputs[manifest.plugin_id][str(param.get("key"))] = (param, widget)
                card.add_widget(row)
        elif not custom_widget and not params:
            hint = Label(
                text="No parameters declared in manifest.",
                size_hint_y=None,
                height="24dp",
                halign="left",
                valign="middle",
                color=MUTED,
                font_name=FONT,
            )
            hint.bind(size=lambda inst, _v: setattr(inst, "text_size", (inst.width, inst.height)))
            card.add_widget(hint)

        actions = BoxLayout(size_hint_y=None, height="40dp", spacing="8dp")
        has_save = (custom_widget is not None and hasattr(custom_widget, "save")) or (not custom_widget and bool(params))
        if has_save:
            save_btn = self._small_btn("Save", solid=True)
            save_btn.size_hint = (1, None)
            save_btn.width = 0
            if custom_widget is not None:
                save_btn.bind(on_release=lambda *_b, w=custom_widget, pid=manifest.plugin_id: (w.save(), self._set_status(f"Saved settings for {pid}")))
            else:
                save_btn.bind(on_release=lambda *_b, pid=manifest.plugin_id: self._save_plugin(pid))
            actions.add_widget(save_btn)
        reload_btn = self._small_btn("Reload")
        reload_btn.size_hint = (1, None)
        reload_btn.width = 0
        reload_btn.bind(on_release=lambda *_b, pid=manifest.plugin_id: self._run_async(self._do_reload(pid)))
        remove_btn = self._small_btn("Remove")
        remove_btn.size_hint = (1, None)
        remove_btn.width = 0
        remove_btn.bind(on_release=lambda *_b, pid=manifest.plugin_id, name=manifest.name: self._confirm_remove(pid, name))
        actions.add_widget(reload_btn)
        actions.add_widget(remove_btn)
        card.add_widget(actions)

        self._recalc_card(card)
        return card

    def _recalc_card(self, card: BoxLayout) -> None:
        def _recalc(*_a):
            total = card.padding[1] + card.padding[3]
            for child in card.children:
                total += child.height
            total += card.spacing * max(0, len(card.children) - 1)
            card.height = total
        card.bind(children=lambda *_: _recalc())
        for child in list(card.children):
            child.bind(height=lambda *_: _recalc())
        _recalc()

    def _build_param_row(self, param: dict[str, Any], value: Any) -> tuple[BoxLayout, Any]:
        key = str(param.get("key", ""))
        label_text = str(param.get("label") or key)
        ptype = str(param.get("type") or "string").lower()
        row = BoxLayout(orientation="vertical", size_hint_y=None, spacing="4dp")

        lbl = Label(
            text=label_text,
            size_hint_y=None,
            height="20dp",
            halign="left",
            valign="middle",
            color=MUTED,
            font_name=FONT,
        )
        lbl.bind(size=lambda inst, _v: setattr(inst, "text_size", (inst.width, inst.height)))
        row.add_widget(lbl)

        widget: Any
        if ptype in ("bool", "boolean"):
            container = BoxLayout(size_hint_y=None, height="34dp")
            widget = BoolToggle(active=bool(value))
            container.add_widget(Label())
            container.add_widget(widget)
            row.add_widget(container)
            row.height = "58dp"
        elif ptype in ("choice", "select", "enum"):
            options = [str(x) for x in (param.get("options") or [])]
            cur = str(value) if value is not None else (options[0] if options else "")
            widget = Spinner(
                text=cur or "Select",
                values=options,
                size_hint_y=None,
                height="36dp",
                background_normal="",
                background_color=BG,
                color=PRIMARY,
                font_name=FONT,
            )
            _outline(widget, MUTED)
            row.add_widget(widget)
            row.height = "64dp"
        else:
            text_val = "" if value is None else str(value)
            widget = TextInput(
                text=text_val,
                multiline=False,
                size_hint_y=None,
                height="36dp",
                background_normal="",
                background_active="",
                background_color=BG,
                foreground_color=PRIMARY,
                cursor_color=PRIMARY,
                padding=["10dp", "8dp"],
                font_name=FONT,
            )
            _outline(widget, MUTED)
            if ptype in ("int", "integer"):
                widget.input_filter = "int"
            elif ptype in ("float", "number"):
                widget.input_filter = "float"
            row.add_widget(widget)
            row.height = "64dp"

        return row, widget

    def _save_plugin(self, plugin_id: str) -> None:
        entries = self._inputs.get(plugin_id, {})
        for key, (param, widget) in entries.items():
            ptype = str(param.get("type") or "string").lower()
            try:
                if ptype in ("bool", "boolean"):
                    val: Any = bool(getattr(widget, "active", False))
                elif ptype in ("int", "integer"):
                    txt = str(getattr(widget, "text", "")).strip()
                    val = int(txt) if txt != "" else param.get("default", 0)
                elif ptype in ("float", "number"):
                    txt = str(getattr(widget, "text", "")).strip()
                    val = float(txt) if txt != "" else param.get("default", 0.0)
                else:
                    val = getattr(widget, "text", "")
            except Exception:
                val = param.get("default")
            self.plugin_manager.set_plugin_setting(plugin_id, key, val)
        self.plugin_manager.context.data.setdefault("plugin_settings", {})[
            plugin_id
        ] = self.plugin_manager.get_plugin_settings(plugin_id)
        print(f"[PluginSettings] saved settings for '{plugin_id}'")
        self._set_status(f"Saved settings for {plugin_id}")
