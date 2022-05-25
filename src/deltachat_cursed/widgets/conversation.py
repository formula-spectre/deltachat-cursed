import textwrap
from datetime import timezone
from typing import List, Optional

import urwid
from deltachat import Chat
from emoji import demojize

from ..account import Account
from ..event import ChatListMonitor
from ..scli import LazyEvalListWalker, ListBoxPlus
from ..util import get_sender_name, is_multiuser


class ConversationWidget(ListBoxPlus, ChatListMonitor):
    """Widget used to print the message list"""

    def __init__(  # noqa
        self,
        date_format: str,
        keymap: dict,
        theme: dict,
        account: Account,
        display_emoji: bool,
    ) -> None:
        self.DATE_FORMAT = date_format
        self.theme = theme
        self.keymap = keymap
        self.account = account
        self.display_emoji = display_emoji
        self.updating = False
        super().__init__(
            LazyEvalListWalker(urwid.MonitoredList(), self._get_message_widget, -1)
        )

    def chatlist_changed(
        self, current_chat_index: Optional[int], chats: List[Chat]
    ) -> None:
        self._update(current_chat_index, chats)
        if current_chat_index is not None:
            chats[current_chat_index].mark_noticed()

    def chat_selected(self, index: Optional[int], chats: List[Chat]) -> None:
        self._update(index, chats)
        if index is not None:
            chats[index].mark_noticed()

    def _update(self, current_chat_index: Optional[int], chats: List[Chat]) -> None:
        if self.updating:
            return

        self.updating = True

        if current_chat_index is None:
            msgs = []
        else:
            msgs = self.account.get_messages(chats[current_chat_index].id)
        self.contents = urwid.MonitoredList(msgs)

        self.updating = False

    def _get_message_widget(self, msg_id: int, _position: int = None) -> urwid.Widget:
        msg = self.account.get_message_by_id(msg_id)
        sender = msg.get_sender_contact()

        local_date = msg.time_sent.replace(tzinfo=timezone.utc).astimezone()
        if msg.is_encrypted() or sender.id < 10:
            timestamp = local_date.strftime(" %H:%M ")
            timestamp_wgt = urwid.Text(("encrypted", timestamp))
        else:
            timestamp = local_date.strftime("!%H:%M ")
            timestamp_wgt = urwid.Text(("unencrypted", timestamp))

        color = self._get_name_color(sender.id)
        name = get_sender_name(msg)
        name = textwrap.shorten(
            name if self.display_emoji else demojize(name),
            80,
        )
        components: list = [(urwid.AttrSpec(*color), name)]
        if msg.is_out_mdn_received():
            components.append("  ✓✓")
        elif msg.is_out_delivered():
            components.append("  ✓")
        elif msg.is_out_pending():
            components.append("  →")
        elif msg.is_out_failed():
            components.append(("failed", "  ✖"))
        header_wgt = urwid.Text(components)

        text = msg.text
        if msg.filename:
            text = f"[file://{msg.filename}]{' – ' if text else ''}{text}"
        if not self.display_emoji:
            text = demojize(text)
        lines = []
        quote_sender = msg.quote and msg.quote.get_sender_contact()
        if msg.quoted_text:
            if quote_sender:
                quote_color = urwid.AttrSpec(*self._get_name_color(quote_sender.id))
                lines.append((quote_color, f"│ {get_sender_name(msg.quote)}\n"))
            else:
                quote_color = "quote"
            lines.append((quote_color, "│ "))
            lines.append(("quote", f"{textwrap.shorten(msg.quoted_text, 150)}\n"))
        if msg.is_system_message():
            lines.append(("system_msg", text))
        else:
            me = self.account.get_self_contact()
            dname = self.account.get_config("displayname")
            if sender == me:
                lines.append(("self_msg", text))
            elif is_multiuser(msg.chat) and (
                (dname and f"@{dname}" in text) or (quote_sender and quote_sender == me)
            ):
                lines.append(("mention", text))
            else:
                lines.append(text)
        body_wgt = urwid.Text(lines or "")

        msg.mark_seen()
        return urwid.Columns(
            [(len(timestamp), timestamp_wgt), urwid.Pile([header_wgt, body_wgt])]
        )

    def _get_name_color(self, id_: int) -> list:
        if id_ == self.account.get_self_contact().id:
            return self.theme["self_color"]

        users_color = self.theme["users_color"]
        color = id_ % len(users_color)
        return users_color[color]

    def keypress(self, size: list, key: str) -> Optional[str]:
        key = super().keypress(size, key)
        if key == self.keymap["down"]:
            self.keypress(size, "down")
        elif key == self.keymap["up"]:
            self.keypress(size, "up")
        else:
            return key
        return None

    def mouse_event(self, size, event, button, col, row, focus) -> None:
        if button == 4:
            self.keypress(size, "up")
            self.keypress(size, "up")
        if button == 5:
            self.keypress(size, "down")
            self.keypress(size, "down")