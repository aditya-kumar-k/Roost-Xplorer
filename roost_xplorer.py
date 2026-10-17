#!/usr/bin/env python3
"""Roost Xplorer - a sleek, dark file manager for Linux (GTK 4 + libadwaita)."""
import codecs
import collections
import ctypes
import ctypes.util
import errno
import fnmatch
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

APP_ID = "io.github.aditya_kumar_k.RoostXplorer"
VERSION = "0.1.0"
REPO_URL = "https://github.com/aditya-kumar-k/roost-xplorer"
ATTRS = ",".join([
    "standard::name", "standard::display-name", "standard::icon",
    "standard::fast-content-type", "standard::size", "standard::type",
    "standard::is-hidden", "standard::is-backup", "standard::is-symlink",
    "time::modified", "thumbnail::path", "thumbnail::failed", "trash::orig-path",
])
NOFOLLOW = Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS
DND_ACTIONS = Gdk.DragAction.COPY | Gdk.DragAction.MOVE

ASSETS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "assets")
LOGO = os.path.join(ASSETS, "icons", "hicolor", "scalable", "apps", APP_ID + ".svg")

CSS = """
/* ---- Roost palette: near-black surfaces, steel-gray accents ---- */
@define-color accent_bg_color #8b9099;
@define-color accent_color #c3c8d1;
@define-color accent_fg_color #0b0b0d;
:root {
  --accent-bg-color: #8b9099;
  --accent-color: #c3c8d1;
  --accent-fg-color: #0b0b0d;
  --window-bg-color: #0b0b0d;
  --window-fg-color: #ececec;
  --view-bg-color: #09090b;
  --view-fg-color: #ececec;
  --headerbar-bg-color: #121215;
  --headerbar-fg-color: #f2f2f2;
  --headerbar-border-color: rgba(139, 144, 153, 0.35);
  --headerbar-backdrop-color: #0e0e10;
  --headerbar-shade-color: rgba(0, 0, 0, 0.6);
  --headerbar-darker-shade-color: rgba(0, 0, 0, 0.7);
  --sidebar-bg-color: #0f0f12;
  --sidebar-fg-color: #ececec;
  --sidebar-backdrop-color: #0c0c0e;
  --sidebar-border-color: rgba(139, 144, 153, 0.22);
  --sidebar-shade-color: rgba(0, 0, 0, 0.5);
  --card-bg-color: #16161a;
  --card-fg-color: #ececec;
  --popover-bg-color: #16161a;
  --popover-fg-color: #f0f0f0;
  --dialog-bg-color: #131316;
  --dialog-fg-color: #f0f0f0;
  --thumbnail-bg-color: #1a1a1e;
  --shade-color: rgba(0, 0, 0, 0.5);
  --scrollbar-outline-color: #000;
}

gridview > child { border-radius: 12px; margin: 2px; padding: 8px 4px; }
gridview > child:hover { background-color: alpha(@accent_bg_color, 0.07); }
gridview > child:selected {
  background-color: alpha(@accent_bg_color, 0.16);
  box-shadow: inset 0 0 0 1px alpha(@accent_bg_color, 0.75);
  color: #fff;
}
columnview row:selected, listview row:selected, .navigation-sidebar row:selected {
  background-color: alpha(@accent_bg_color, 0.16);
  box-shadow: inset 3px 0 0 @accent_bg_color;
  color: #fff;
}
.navigation-sidebar row:selected image { color: @accent_color; }
.navigation-sidebar row.drop-line-before { box-shadow: inset 0 2px 0 @accent_color; }
.navigation-sidebar row.drop-line-after { box-shadow: inset 0 -2px 0 @accent_color; }
.navigation-sidebar row.dragging { opacity: 0.45; }
.navigation-sidebar row .drop-hover, .navigation-sidebar row.drop-hover, .navigation-sidebar .drop-hover {
  background-color: alpha(@accent_bg_color, 0.25);
  box-shadow: inset 0 0 0 1px @accent_bg_color;
}
.folder-icon { filter: grayscale(1) brightness(1.1) contrast(0.95); }

.status-bar { padding: 5px 14px; font-size: 0.85em; opacity: 0.7; }
.crumb { padding: 2px 10px; min-height: 28px; border-radius: 8px; }
.crumb-current { font-weight: bold; color: @accent_color; }
.crumb-sep { opacity: 0.4; color: @accent_color; }
.pane-title { padding: 6px 14px 2px 14px; }
.pane-active { border-top: 2px solid @accent_bg_color; }
.pane-inactive { border-top: 2px solid transparent; }
.pane-inactive .status-bar, .pane-inactive .pane-title { opacity: 0.45; }
/* soft colour changes on hover and selection instead of instant jumps */
gridview > child, columnview row, .navigation-sidebar row, headerbar button, .crumb, windowcontrols button {
  transition: background-color 140ms ease, box-shadow 140ms ease, color 140ms ease;
}
.eject-button { min-width: 26px; min-height: 26px; padding: 0; margin: 0; }
.eject-button:hover { color: @accent_color; }
progressbar.disk-usage trough { min-height: 4px; border-radius: 2px; background-color: alpha(white, 0.14); }
progressbar.disk-usage progress { min-height: 4px; border-radius: 2px; background-color: @accent_bg_color; }
progressbar.disk-usage.full progress { background-color: #e5484d; }
.brand-title { color: @accent_color; letter-spacing: 2px; font-weight: 800; }
headerbar { box-shadow: inset 0 -1px alpha(@accent_bg_color, 0.35); }

/* ---- window buttons: flat, full-height, flush with the corner (Fitts's law: slam the mouse into the corner) ---- */
headerbar > windowhandle > box { padding-top: 0; padding-bottom: 0; padding-right: 0; }
headerbar windowcontrols.end { margin-left: 6px; }
headerbar windowcontrols button {
  margin: 0;
  padding: 0;
  min-width: 46px;
  min-height: 46px;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  color: @headerbar_fg_color;
}
headerbar windowcontrols button image {  /* the round bubble is drawn on the icon inside the button */
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  padding: 0;
  margin: 0;
  min-width: 46px;
  min-height: 40px;
}
headerbar windowcontrols button:hover { background-color: alpha(@accent_bg_color, 0.22); }
headerbar windowcontrols button.close:hover { background-color: #c01c28; color: #fff; }
headerbar windowcontrols button:active { background-color: alpha(@accent_bg_color, 0.35); }
headerbar windowcontrols button.close:active { background-color: #9b1620; }
searchbar > revealer > box { background-color: #121215; }
"""

# The translucent look: the window background is about 78% opaque, the file area is left clear and the sidebar
# and header add a light tint on top. Popups and dialogs keep their solid backgrounds so text stays readable.
CSS += """
window.translucent {
  --window-bg-color: rgba(11, 11, 13, 0.78);
  --view-bg-color: rgba(9, 9, 11, 0);
  --headerbar-bg-color: rgba(18, 18, 21, 0.38);
  --headerbar-backdrop-color: rgba(14, 14, 16, 0.38);
  --sidebar-bg-color: rgba(15, 15, 18, 0.28);
  --sidebar-backdrop-color: rgba(12, 12, 14, 0.28);
}
"""

THUMB_CACHE = {}
POOL = ThreadPoolExecutor(max_workers=2)
TYPE_DESC = {}


# ----------------------------------------------------------------- helpers
def mount_is_removable(mount):
    """USB sticks, SD cards, other external media and network shares get an eject button; internal disks don't."""
    try:
        if mount.can_eject():
            return True
        drive = mount.get_drive()
        if drive is not None:
            return bool(drive.is_removable())
        return mount.get_volume() is None and mount.can_unmount()  # network and virtual mounts
    except (GLib.Error, AttributeError):
        return False


def disk_key(obj, root=None):
    """A stable id for a disk, so a custom label survives re-mounting and changing mount points."""
    uuid = None
    try:
        uuid = obj.get_uuid()
        if not uuid and hasattr(obj, "get_volume") and obj.get_volume() is not None:
            uuid = obj.get_volume().get_uuid()
        if not uuid and hasattr(obj, "get_identifier"):
            uuid = obj.get_identifier("uuid")
    except (GLib.Error, AttributeError):
        pass
    if uuid:
        return "uuid:" + uuid
    path = root.get_path() if root is not None else None
    return "path:" + path if path else None


def ctrl_held(target=None):
    """Is Ctrl down right now? (A drop isn't a normal input event, so ask the keyboard itself.)"""
    try:
        keyboard = Gdk.Display.get_default().get_default_seat().get_keyboard()
        if keyboard is not None and keyboard.get_modifier_state() & Gdk.ModifierType.CONTROL_MASK:
            return True
    except (AttributeError, GLib.Error):
        pass
    try:
        return bool(target is not None and target.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK)
    except AttributeError:
        return False


def info_file(info):
    return info.get_attribute_object("standard::file")


def is_dir(info):
    return info.get_file_type() == Gio.FileType.DIRECTORY


def content_type(info):
    return info.get_attribute_string("standard::fast-content-type") or ""


def type_description(info):
    if is_dir(info):
        return "Folder"
    ct = content_type(info)
    if ct not in TYPE_DESC:
        TYPE_DESC[ct] = Gio.content_type_get_description(ct) if ct else "Unknown"
    return TYPE_DESC[ct]


def mtime(info):
    dt = info.get_modification_date_time()
    return dt.to_unix() if dt else 0


def fmt_date(info):
    dt = info.get_modification_date_time()
    if not dt:
        return ""
    dt = dt.to_local()
    now = GLib.DateTime.new_now_local()
    if dt.get_year() == now.get_year():
        if dt.get_day_of_year() == now.get_day_of_year():
            return dt.format("%H:%M")
        return dt.format("%b %-d")
    return dt.format("%b %-d, %Y")


def display_name(file):
    path = file.get_path()
    if path == GLib.get_home_dir():
        return "Home"
    if path == "/":
        return "File System"
    if file.get_uri_scheme() == "trash" and file.get_parent() is None:
        return "Trash"
    try:
        return file.query_info("standard::display-name", 0, None).get_display_name()
    except GLib.Error:
        return file.get_basename() or file.get_uri()


def split_extension(name):
    """('photo', '.jpg'), but also ('backup', '.tar.gz') so numbering goes before the whole extension."""
    low = name.lower()
    for compound in (".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst"):
        if low.endswith(compound) and len(name) > len(compound):
            return name[: -len(compound)], name[-len(compound):]
    return os.path.splitext(name)


def unique_dest(dest_dir, name, directory):
    target = dest_dir.get_child(name)
    if not target.query_exists(None):
        return target
    stem, ext = (name, "") if directory else split_extension(name)
    i = 1
    while True:
        target = dest_dir.get_child(f"{stem} ({i}){ext}")
        if not target.query_exists(None):
            return target
        i += 1


def file_is_dir(f):
    return f.query_file_type(NOFOLLOW, None) == Gio.FileType.DIRECTORY


class Cancelled(Exception):
    """Raised inside a job when the user pressed Cancel."""


class Job:
    """A background file operation: progress, cancellation and the info needed to undo it."""

    def __init__(self, title):
        self.title = title
        self.status = "Preparing…"
        self.total = 0
        self.done = 0
        self.cancellable = Gio.Cancellable()
        self.started = GLib.get_monotonic_time()
        self.error = None
        self.cancelled = False
        self.undo = None      # undo entry to remember when the job ends
        self.resolver = None  # callback asked when a name already exists at the destination
        self.sticky = None    # an "apply to all" answer
        self.multi = False
        self.unit = "items"  # "bytes" for copies and moves
        self.samples = []    # (time, done) pairs for speed and time-left
        self.message = None   # what to tell the user on success

    def detail(self):
        """A live one-line summary: 1.2 GB of 4.0 GB · 45 MB/s · about 1 min left."""
        now = GLib.get_monotonic_time()
        self.samples.append((now, self.done))
        self.samples = [x for x in self.samples if now - x[0] <= 4_000_000]  # speed over the last few seconds
        if self.unit == "bytes":
            text = f"{GLib.format_size(self.done)} of {GLib.format_size(self.total)}"
        else:
            text = f"{self.done} of {self.total} items"
        if len(self.samples) >= 2 and self.samples[-1][0] > self.samples[0][0]:
            dt = (self.samples[-1][0] - self.samples[0][0]) / 1_000_000
            rate = (self.samples[-1][1] - self.samples[0][1]) / dt
            if rate > 0 and self.unit == "bytes":
                text += f" · {GLib.format_size(int(rate))}/s"
            if rate > 0 and self.total > self.done:
                left = (self.total - self.done) / rate
                text += " · " + ("a few seconds left" if left < 8 else f"about {int(left)} s left" if left < 90
                                  else f"about {int(left / 60 + 0.5)} min left")
        return text

    @property
    def fraction(self):
        return min(1.0, self.done / self.total) if self.total else 0.0

    def check(self):
        if self.cancellable.is_cancelled():
            raise Cancelled()


def _cancel_or_raise(e):
    if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
        raise Cancelled() from e
    raise e


def animate_fraction(bar, target, duration=170):
    """Glide a progress bar to a new value instead of jumping."""
    current = bar.get_fraction()
    if abs(target - current) < 0.002:
        return
    old = getattr(bar, "_anim", None)
    if old is not None:
        old.skip()
    anim = Adw.TimedAnimation.new(bar, current, target, duration, Adw.CallbackAnimationTarget.new(bar.set_fraction))
    anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
    bar._anim = anim
    anim.play()


def tree_size(f, job=None):
    """Total bytes of a file or folder (not following symlinks)."""
    if job:
        job.check()
    try:
        info = f.query_info("standard::type,standard::size", NOFOLLOW, None)
    except GLib.Error:
        return 0
    if info.get_file_type() != Gio.FileType.DIRECTORY:
        return info.get_size()
    total = 0
    try:
        en = f.enumerate_children("standard::name", NOFOLLOW, None)
        while (ci := en.next_file(None)) is not None:
            total += tree_size(f.get_child(ci.get_name()), job)
    except GLib.Error:
        pass
    return total


SEARCH_LIMIT = 5000           # stop a search after this many results
SEARCH_BATCH = 12             # results handed to the window at a time: small, so the window never stalls
TEXT_PREVIEW_LIMIT = 200_000   # bytes of a text file shown in the quick preview
IMAGE_PREVIEW_MAX = 2400       # longest side, in pixels, of an image preview
FAV_DRAG_PREFIX = "roost-favorite:"   # marks a favorite being dragged to a new place in the list
ZOOM_STEPS = (40, 56, 72, 96, 128, 160, 200)   # icon sizes in the grid view (72 is the default)
CHUNK = 4 * 1024 * 1024        # how much is copied between progress updates
SYNC_EVERY = 16 * 1024 * 1024  # flush to a *different* drive this often, so progress reflects real writes


def copy_regular_local(src_path, dst_path, job):
    """Copy a local file in chunks, reporting progress after every chunk.

    GIO's own copy only reports occasionally (sometimes only at the end), and the kernel's write cache
    soaks up the first hundreds of MB instantly, so the bar used to jump to 20-30% and then stall.
    Flushing regularly makes the bar follow what has really reached the drive. On the same drive,
    copy_file_range still lets the filesystem do instant copy-on-write copies."""
    same_drive = os.stat(src_path).st_dev == os.stat(os.path.dirname(dst_path) or ".").st_dev
    sfd = os.open(src_path, os.O_RDONLY)
    dfd = None
    try:
        mode = os.fstat(sfd).st_mode & 0o7777
        dfd = os.open(dst_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode or 0o600)
        use_range = hasattr(os, "copy_file_range")
        base, copied, since_sync = job.done, 0, 0
        sync_every, last_sync = SYNC_EVERY, time.monotonic()
        while True:
            job.check()
            if use_range:
                try:
                    n = os.copy_file_range(sfd, dfd, CHUNK)
                except OSError:  # e.g. a filesystem that can't do it: use plain reads and writes
                    use_range = False
                    continue
            else:
                buf = os.read(sfd, CHUNK)
                n = len(buf)
                view = memoryview(buf)
                while view:
                    view = view[os.write(dfd, view):]
            if n == 0:
                break
            copied += n
            since_sync += n
            job.done = base + copied
            if not same_drive and since_sync >= sync_every:
                os.fdatasync(dfd)
                now = time.monotonic()
                rate = since_sync / max(now - last_sync, 1e-3)
                # a slow drive (USB stick, network) gets flushed every chunk so the bar stays smooth
                sync_every = CHUNK if rate < 40 * 1024 * 1024 else SYNC_EVERY
                last_sync, since_sync = now, 0
        if not same_drive and since_sync:
            job.status = f"Writing {os.path.basename(dst_path)} to the drive…"
            os.fsync(dfd)
    except BaseException:
        if dfd is not None:
            os.close(dfd)
            dfd = None
        try:
            os.unlink(dst_path)  # never leave a half-written file behind
        except OSError:
            pass
        raise
    finally:
        os.close(sfd)
        if dfd is not None:
            os.close(dfd)
    try:
        shutil.copystat(src_path, dst_path)  # permissions, times, extended attributes
    except OSError:
        pass


def copy_regular_stream(src, dst, job):
    """Same idea for non-local locations (network shares, phones): chunked, with progress."""
    ins = src.read(job.cancellable)
    outs = None
    try:
        outs = dst.create(Gio.FileCreateFlags.NONE, job.cancellable)
        while True:
            data = ins.read_bytes(CHUNK, job.cancellable)
            n = data.get_size()
            if n == 0:
                break
            outs.write_all(data.get_data(), job.cancellable)
            job.done += n
        outs.close(job.cancellable)
    finally:
        ins.close(None)
        if outs is not None and not outs.is_closed():
            outs.close(None)
    try:
        src.copy_attributes(dst, Gio.FileCopyFlags.ALL_METADATA, job.cancellable)
    except GLib.Error:
        pass


def copy_tree(src, dst, job=None):
    if job:
        job.check()
    kind = src.query_info("standard::type", NOFOLLOW, None).get_file_type()
    if kind == Gio.FileType.DIRECTORY:
        dst.make_directory_with_parents(None)
        en = src.enumerate_children("standard::name", NOFOLLOW, None)
        while (ci := en.next_file(None)) is not None:
            copy_tree(src.get_child(ci.get_name()), dst.get_child(ci.get_name()), job)
        return
    if job:
        job.status = f"Copying {src.get_basename()}"
    if job and kind == Gio.FileType.REGULAR:
        try:
            if src.get_path() and dst.get_path():
                copy_regular_local(src.get_path(), dst.get_path(), job)
            else:
                copy_regular_stream(src, dst, job)
            return
        except GLib.Error as e:
            _cancel_or_raise(e)
    # symlinks, special files, or no job: let GIO do it
    base = job.done if job else 0
    callback = (lambda cur, tot, _: setattr(job, "done", base + cur)) if job else None
    try:
        src.copy(dst, Gio.FileCopyFlags.NOFOLLOW_SYMLINKS | Gio.FileCopyFlags.ALL_METADATA,
                 job.cancellable if job else None, callback, None)
    except GLib.Error as e:
        _cancel_or_raise(e)
    if job:
        job.done = base + src.query_info("standard::size", NOFOLLOW, None).get_size()


def delete_tree(f, job=None):
    if job:
        job.check()
    if file_is_dir(f):
        en = f.enumerate_children("standard::name", NOFOLLOW, None)
        while (ci := en.next_file(None)) is not None:
            delete_tree(f.get_child(ci.get_name()), job)
    f.delete(job.cancellable if job else None)


def quiet_delete(f):
    try:
        if f.query_exists(None):
            delete_tree(f)
    except GLib.Error:
        pass


def plural(n, word="item"):
    return f"{n} {word}{'s' if n != 1 else ''}"


def newest_trash_name(orig_path):
    """Name of the most recently trashed item that came from orig_path."""
    root = Gio.File.new_for_uri("trash:///")
    en = root.enumerate_children("standard::name,trash::orig-path,trash::deletion-date", 0, None)
    best = (None, "")
    while (ci := en.next_file(None)) is not None:
        if ci.get_attribute_byte_string("trash::orig-path") == orig_path:
            when = ci.get_attribute_string("trash::deletion-date") or ""
            if best[0] is None or when >= best[1]:
                best = (ci.get_name(), when)
    return best[0]


def transfer_job(job, files, dest_dir, move):
    items = []
    for f in files:
        parent = f.get_parent()
        if move and parent is not None and parent.equal(dest_dir):
            continue
        if file_is_dir(f) and (dest_dir.equal(f) or dest_dir.has_prefix(f)):
            raise RuntimeError(f"Can't put “{f.get_basename()}” inside itself")
        items.append((f, tree_size(f, job)))
    job.total = sum(size for _, size in items) or 1
    job.multi = len(items) > 1
    job.unit = "bytes"
    created, moved, replaced = [], [], []

    def transfer_one(src, dst):
        job.status = f"{'Moving' if move else 'Copying'} {src.get_basename()}"
        if move:
            size = tree_size(src)
            if src.get_path() and dst.get_path():
                try:
                    os.rename(src.get_path(), dst.get_path())  # same drive: instant
                    job.done += size
                    moved.append((src, dst))
                    return
                except OSError as e:
                    if e.errno != errno.EXDEV:
                        raise
                    # different drive: copy (with real progress), then delete the original
            else:
                base = job.done
                try:
                    src.move(dst, Gio.FileCopyFlags.NONE, job.cancellable,
                             lambda cur, tot, _: setattr(job, "done", base + cur), None)
                    job.done = base + size
                    moved.append((src, dst))
                    return
                except GLib.Error as e:
                    if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                        raise Cancelled() from e
                    # fall back to copy + delete
        try:
            copy_tree(src, dst, job)
        except Cancelled:
            quiet_delete(dst)
            raise
        if move:
            delete_tree(src, job)
            moved.append((src, dst))
        else:
            created.append(dst)

    def choose(src, target):
        both_dirs = file_is_dir(src) and file_is_dir(target)
        if job.sticky == "merge" and both_dirs:
            return "merge"
        if job.sticky in ("skip", "keep", "replace"):
            return job.sticky
        if job.resolver is None:
            return "keep"
        choice, apply_all = job.resolver(job, src, target, both_dirs)
        if apply_all:
            job.sticky = choice
        return choice

    def replace(target):
        """Replacing sends the old item to the Trash first, so nothing is lost and Undo can bring it back."""
        path = target.get_path()
        try:
            target.trash(job.cancellable)
            name = newest_trash_name(path)
            if name:
                replaced.append((path, name))
        except GLib.Error as e:
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                raise Cancelled() from e
            delete_tree(target)  # no trash on this drive: replace in place

    def place(src, into):
        job.check()
        name = src.get_basename()
        directory = file_is_dir(src)
        target = into.get_child(name)
        if src.equal(target):  # copying into the folder it already lives in
            transfer_one(src, unique_dest(into, name, directory))
        elif target.query_exists(None):
            choice = choose(src, target)
            if choice == "skip":
                job.done += tree_size(src)
            elif choice == "keep":
                transfer_one(src, unique_dest(into, name, directory))
            elif choice == "merge":
                en = src.enumerate_children("standard::name", NOFOLLOW, None)
                while (ci := en.next_file(None)) is not None:
                    place(src.get_child(ci.get_name()), target)
                if move:
                    try:
                        src.delete(None)  # only succeeds once everything inside has moved out
                    except GLib.Error:
                        pass
            else:  # replace
                replace(target)
                transfer_one(src, target)
        else:
            transfer_one(src, target)

    try:
        for f, _size in items:
            place(f, dest_dir)
    finally:
        entry = None
        if moved:
            entry = {"kind": "move", "pairs": moved}
        elif created:
            entry = {"kind": "copy", "created": created}
        if entry is not None:
            entry["replaced"] = replaced
        job.undo = entry
    job.message = f"{'Moved' if move else 'Copied'} {plural(len(moved) or len(created))}"


def restore_replaced(job, replaced):
    """Bring back the items that a Replace had sent to the Trash."""
    root = Gio.File.new_for_uri("trash:///")
    for path, name in replaced:
        job.check()
        item = root.get_child(name)
        if not item.query_exists(None):
            continue
        dest = Gio.File.new_for_path(path)
        if dest.query_exists(None):
            dest = unique_dest(dest.get_parent(), dest.get_basename(), file_is_dir(item))
        job.status = f"Restoring {dest.get_basename()}"
        try:
            item.move(dest, Gio.FileCopyFlags.NONE, job.cancellable, None, None)
        except GLib.Error as e:
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                raise Cancelled() from e
            copy_tree(item, dest, job)
            delete_tree(item, job)


def trash_job(job, files, permanent):
    job.total = len(files)
    trashed = []
    try:
        for f in files:
            job.check()
            job.status = f"{'Deleting' if permanent else 'Moving to Trash:'} {f.get_basename()}"
            if permanent:
                delete_tree(f, job)
            else:
                try:
                    f.trash(job.cancellable)
                except GLib.Error as e:
                    _cancel_or_raise(e)
                trashed.append(f.get_path())
            job.done += 1
    finally:
        if trashed:
            job.undo = {"kind": "trash", "paths": trashed}
    job.message = f"{'Deleted' if permanent else 'Moved to Trash:'} {plural(len(files))}"


def restore_from_trash(job, wanted):
    """Move the newest trashed copy of each original path back where it came from."""
    root = Gio.File.new_for_uri("trash:///")
    en = root.enumerate_children("standard::name,standard::type,trash::orig-path,trash::deletion-date", 0, None)
    best = {}
    while (ci := en.next_file(None)) is not None:
        orig = ci.get_attribute_byte_string("trash::orig-path")
        when = ci.get_attribute_string("trash::deletion-date") or ""
        if orig in wanted and (orig not in best or when >= best[orig][0]):
            best[orig] = (when, root.get_child(ci.get_name()), ci.get_file_type() == Gio.FileType.DIRECTORY)
    job.total = len(best) or 1
    restored = []
    for orig, (_, f, directory) in best.items():
        job.check()
        dest = Gio.File.new_for_path(orig)
        parent = dest.get_parent()
        if not parent.query_exists(None):
            parent.make_directory_with_parents(None)
        if dest.query_exists(None):
            dest = unique_dest(parent, dest.get_basename(), directory)
        job.status = f"Restoring {dest.get_basename()}"
        try:
            f.move(dest, Gio.FileCopyFlags.NONE, job.cancellable, None, None)
        except GLib.Error as e:
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                raise Cancelled() from e
            copy_tree(f, dest, job)
            delete_tree(f, job)
        restored.append(dest.get_path())
        job.done += 1
    job.undo = {"kind": "trash", "paths": restored} if restored else None
    job.message = f"Restored {plural(len(restored))}"


# ---------------------------------------------------------------- archives
ARCHIVE_FORMATS = {"zip": ".zip", "tar.gz": ".tar.gz", "tar.xz": ".tar.xz"}
TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar.zst", ".tzst")
EXTERNAL_SUFFIXES = (".7z", ".rar", ".iso", ".cab", ".arj", ".lzh")


def external_extractor():
    """The 7-Zip command line tool, if installed: it opens 7z, rar and many other formats."""
    return shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")


def archive_kind(name):
    low = name.lower()
    if low.endswith(".zip"):
        return "zip"
    if low.endswith(TAR_SUFFIXES):
        return "tar"
    if low.endswith(EXTERNAL_SUFFIXES) and external_extractor():
        return "external"
    return None


def archive_stem(name):
    low = name.lower()
    for suffix in sorted((".zip",) + TAR_SUFFIXES + EXTERNAL_SUFFIXES, key=len, reverse=True):
        if low.endswith(suffix):
            return name[: -len(suffix)] or name
    return name


class _ProgressReader:
    """Wraps a file being read and reports how much has been read to a job (and honours Cancel)."""

    def __init__(self, fileobj, job):
        self.f, self.job = fileobj, job

    def read(self, n=-1):
        self.job.check()
        data = self.f.read(CHUNK if n is None or n < 0 else n)
        self.job.done += len(data)
        return data


def collect_entries(files):
    """Everything to put in an archive as (path, name inside the archive, kind); symlinks are kept as links."""
    entries = []
    for f in files:
        base = f.get_path()
        parent = os.path.dirname(base)
        if os.path.islink(base):
            entries.append((base, os.path.basename(base), "link"))
        elif not os.path.isdir(base):
            if stat.S_ISREG(os.lstat(base).st_mode):
                entries.append((base, os.path.basename(base), "file"))
            continue
        else:
            for root, dirs, names in os.walk(base, followlinks=False):
                rel = os.path.relpath(root, parent)
                entries.append((root, rel, "dir"))
                for d in list(dirs):  # os.walk lists links to folders among the folders but does not enter them
                    full = os.path.join(root, d)
                    if os.path.islink(full):
                        entries.append((full, os.path.join(rel, d), "link"))
                        dirs.remove(d)
                for n in names:
                    full = os.path.join(root, n)
                    if os.path.islink(full):
                        entries.append((full, os.path.join(rel, n), "link"))
                    elif stat.S_ISREG(os.lstat(full).st_mode):
                        entries.append((full, os.path.join(rel, n), "file"))
    return entries


def _write_zip(job, dest, entries):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        for path, arc, kind in entries:
            job.check()
            job.status = f"Adding {os.path.basename(path)}"
            if kind == "dir":
                zf.writestr(zipfile.ZipInfo.from_file(path, arc), b"")
            elif kind == "link":
                info = zipfile.ZipInfo(arc)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                zf.writestr(info, os.readlink(path))
            else:
                info = zipfile.ZipInfo.from_file(path, arc)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(path, "rb") as src, zf.open(info, "w", force_zip64=info.file_size > (1 << 31) - 1) as out:
                    while chunk := src.read(CHUNK):
                        out.write(chunk)
                        job.done += len(chunk)
                        job.check()


def _write_tar(job, dest, entries, mode):
    with tarfile.open(dest, mode) as tar:
        for path, arc, kind in entries:
            job.check()
            job.status = f"Adding {os.path.basename(path)}"
            info = tar.gettarinfo(path, arc)
            if info is None:
                continue
            info.uid = info.gid = 0  # don't put your user name inside archives you may share
            info.uname = info.gname = ""
            if info.isreg():
                with open(path, "rb") as f:
                    tar.addfile(info, _ProgressReader(f, job))
            else:
                tar.addfile(info)


def compress_job(job, files, dest_path, fmt):
    entries = collect_entries(files)
    job.unit = "bytes"
    job.total = sum(os.lstat(p).st_size for p, _a, k in entries if k == "file") or 1
    try:
        if fmt == "zip":
            _write_zip(job, dest_path, entries)
        else:
            _write_tar(job, dest_path, entries, "w:gz" if fmt == "tar.gz" else "w:xz")
    except BaseException:
        quiet_delete(Gio.File.new_for_path(dest_path))  # never leave a half-written archive
        raise
    job.undo = {"kind": "copy", "created": [Gio.File.new_for_path(dest_path)], "replaced": []}
    job.message = f"Created {os.path.basename(dest_path)}"


def _inside(base, path):
    base = os.path.realpath(base)
    path = os.path.realpath(path)
    return path == base or path.startswith(base + os.sep)


def _extract_zip(job, path, dest):
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            job.total += sum(i.file_size for i in infos) or 1
            skipped = 0
            for info in infos:
                job.check()
                target = os.path.join(dest, info.filename)
                if not _inside(dest, target):
                    skipped += 1  # a "../" or absolute path trying to escape the folder
                    continue
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    link = zf.read(info).decode("utf-8", "replace")
                    if _inside(dest, os.path.join(os.path.dirname(target), link)):
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        os.symlink(link, target)
                    else:
                        skipped += 1
                elif info.is_dir():
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(info) as src, open(target, "wb") as out:
                        while chunk := src.read(CHUNK):
                            out.write(chunk)
                            job.done += len(chunk)
                            job.check()
                    if mode & 0o777:
                        os.chmod(target, mode & 0o777)
                    try:
                        ts = time.mktime(info.date_time + (0, 0, -1))
                        os.utime(target, (ts, ts))
                    except (OverflowError, ValueError):
                        pass
            return skipped
    except RuntimeError as e:
        if "password" in str(e).lower() or "encrypted" in str(e).lower():
            raise RuntimeError("This archive is password protected.") from e
        raise
    except zipfile.BadZipFile as e:
        raise RuntimeError("This is not a valid zip file, or it is damaged.") from e


def _extract_tar(job, path, dest):
    skipped = 0
    job.total += os.path.getsize(path) or 1
    try:
        with open(path, "rb") as raw:
            with tarfile.open(fileobj=_ProgressReader(raw, job), mode="r|*") as tar:
                for member in tar:
                    job.check()
                    try:
                        tar.extract(member, dest, filter="data")  # refuses paths and links that escape the folder
                    except tarfile.FilterError:
                        skipped += 1
    except tarfile.ReadError as e:
        raise RuntimeError("This archive is damaged or in a format that is not supported.") from e
    return skipped


def _extract_external(job, path, dest):
    proc = subprocess.Popen([external_extractor(), "x", "-y", f"-o{dest}", "--", path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    while proc.poll() is None:
        if job.cancellable.is_cancelled():
            proc.terminate()
            proc.wait()
            raise Cancelled()
        time.sleep(0.1)
    if proc.returncode != 0:
        detail = (proc.stderr.read() or b"").decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "The archive could not be extracted.")
    return 0


def extract_job(job, archives):
    job.unit = "bytes"
    created, skipped = [], 0
    for f in archives:
        job.check()
        name, parent = f.get_basename(), f.get_parent()
        job.status = f"Extracting {name}"
        # extract beside the archive into a scratch folder first, then decide what to call the result
        tmp = tempfile.mkdtemp(prefix=".roost-extract-", dir=parent.get_path())
        try:
            kind = archive_kind(name)
            skipped += {"zip": _extract_zip, "tar": _extract_tar, "external": _extract_external}[kind](job, f.get_path(), tmp)
            entries = os.listdir(tmp)
            if len(entries) == 1:  # the archive already has one top-level item: don't wrap it in another folder
                src = os.path.join(tmp, entries[0])
                target = unique_dest(parent, entries[0], os.path.isdir(src) and not os.path.islink(src)).get_path()
            else:
                src = tmp
                target = unique_dest(parent, archive_stem(name) or "extracted", True).get_path()
            os.rename(src, target)
            created.append(Gio.File.new_for_path(target))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if created:
        job.undo = {"kind": "copy", "created": created, "replaced": []}
    job.message = f"Extracted {plural(len(created), 'archive')}" + (f" ({skipped} unsafe item{'s' if skipped != 1 else ''} skipped)" if skipped else "")


def undo_job(job, entry):
    kind = entry["kind"]
    if kind == "copy":
        job.total = len(entry["created"])
        for f in entry["created"]:
            job.check()
            if f.query_exists(None):
                job.status = f"Removing {f.get_basename()}"
                f.trash(job.cancellable)
            job.done += 1
        restore_replaced(job, entry.get("replaced", []))
        job.message = "Copy undone"
    elif kind == "move":
        job.total = len(entry["pairs"])
        for src, dst in entry["pairs"]:
            job.check()
            if not dst.query_exists(None):
                job.done += 1
                continue
            parent = src.get_parent()
            if not parent.query_exists(None):
                parent.make_directory_with_parents(None)
            target = unique_dest(parent, src.get_basename(), file_is_dir(dst)) if src.query_exists(None) else src
            job.status = f"Moving back {target.get_basename()}"
            try:
                dst.move(target, Gio.FileCopyFlags.NONE, job.cancellable, None, None)
            except GLib.Error as e:
                if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                    raise Cancelled() from e
                copy_tree(dst, target, job)
                delete_tree(dst, job)
            job.done += 1
        restore_replaced(job, entry.get("replaced", []))
        job.message = "Move undone"
    elif kind == "trash":
        restore_from_trash(job, set(entry["paths"]))
        job.undo = None
        job.message = "Deletion undone"
    elif kind == "rename":
        entry["file"].set_display_name(entry["old"], None)
        job.message = "Rename undone"
    elif kind == "mkdir":
        entry["file"].trash(None)
        job.message = "Folder removed"


def apply_thumb(img, info):
    """Show a real thumbnail for the item if one exists (or can be made)."""
    img._token = None
    f = info_file(info)
    if f is None:
        return
    path = info.get_attribute_byte_string("thumbnail::path")
    if path and not info.get_attribute_boolean("thumbnail::failed"):
        tex = THUMB_CACHE.get(path)
        if tex is None:
            try:
                tex = Gdk.Texture.new_from_filename(path)
            except GLib.Error:
                tex = None
            else:
                THUMB_CACHE[path] = tex
        if tex is not None:
            img.remove_css_class("folder-icon")
            img.set_from_paintable(tex)
            return
    local = f.get_path()
    if local and content_type(info).startswith("image/") and 0 < info.get_size() < 40_000_000:
        tex = THUMB_CACHE.get(local)
        if tex is not None:
            img.remove_css_class("folder-icon")
            img.set_from_paintable(tex)
            return
        img._token = local

        def work():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(local, 256, 256, True)
                pb = pb.apply_embedded_orientation() or pb
            except GLib.Error:
                return
            GLib.idle_add(finish, pb)

        def finish(pb):
            if len(THUMB_CACHE) > 600:
                del THUMB_CACHE[next(iter(THUMB_CACHE))]
            tex = Gdk.Texture.new_for_pixbuf(pb)
            THUMB_CACHE[local] = tex
            if getattr(img, "_token", None) == local:
                img.remove_css_class("folder-icon")
                img.set_from_paintable(tex)

        POOL.submit(work)


def files_value(files):
    return GObject.Value(Gdk.FileList.__gtype__, Gdk.FileList.new_from_list(files))


# --------------------------------------------------------------------- tab
class FolderModel(Gio.ListStore):
    """The contents of one folder, kept live by watching it.

    GTK's own folder list stops updating after certain quick sequences (for example a hidden scratch folder that is
    created and renamed straight away, which is how extracting an archive works). This one handles every kind of
    change itself, and can also re-check the whole folder (resync) to catch anything a watcher missed, which
    matters on network shares and some external drives."""

    loading = GObject.Property(type=bool, default=False)
    error = GObject.Property(type=object)

    def __init__(self):
        super().__init__(item_type=Gio.FileInfo)
        self.file = None
        self._gen = 0
        self._cancel = None
        self._monitor = None
        self._poll = None
        self._resyncing = False

    def is_loading(self):
        return self.props.loading

    def get_error(self):
        return self.props.error

    # ---- loading a folder
    def set_file(self, file):
        self._stop()
        self.file = file
        self.remove_all()
        self.props.error = None
        self.props.loading = True
        gen = self._gen
        try:  # watch for changes (renames and moves included)
            self._monitor = file.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
            self._monitor.connect("changed", self._on_event)
        except GLib.Error:
            self._monitor = None
        if self._monitor is None:  # a place that can't be watched (some network shares): look again every few seconds
            self._poll = GLib.timeout_add_seconds(3, self._poll_tick)
        self._enumerate(gen, file, initial=True)

    def _stop(self):
        self._gen += 1  # answers to anything still in flight are ignored
        if self._cancel is not None:
            self._cancel.cancel()
            self._cancel = None
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None
        if self._poll is not None:
            GLib.source_remove(self._poll)
            self._poll = None
        self._resyncing = False

    def _enumerate(self, gen, folder, initial):
        cancel = self._cancel = Gio.Cancellable()
        collected = []

        def finished(error=None):
            if gen != self._gen:
                return
            if initial:
                self.props.loading = False
                if error is not None:
                    self.props.error = error
            else:
                self._resyncing = False
                if error is None:
                    self._apply_diff(collected)

        def on_enum(f, res):
            if gen != self._gen:
                return
            try:
                enum = f.enumerate_children_finish(res)
            except GLib.Error as e:
                return finished(e)
            enum.next_files_async(500, GLib.PRIORITY_DEFAULT, cancel, on_batch, enum)

        def on_batch(enum, res, _data=None):
            if gen != self._gen:
                return
            try:
                infos = enum.next_files_finish(res)
            except GLib.Error as e:
                return finished(e)
            if not infos:
                enum.close_async(GLib.PRIORITY_DEFAULT, None, None)
                return finished()
            self._prepare(infos, folder)
            if initial:
                self.splice(self.get_n_items(), 0, infos)  # show them as they arrive
            else:
                collected.extend(infos)
            enum.next_files_async(500, GLib.PRIORITY_DEFAULT, cancel, on_batch, enum)

        folder.enumerate_children_async(ATTRS, Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, cancel, on_enum)

    @staticmethod
    def _prepare(infos, folder):
        for info in infos:
            info.set_attribute_object("standard::file", folder.get_child(info.get_name()))

    # ---- keeping it up to date
    def _find(self, name):
        for pos in range(self.get_n_items()):
            if self.get_item(pos).get_name() == name:
                return pos
        return None

    @staticmethod
    def _same(a, b):
        return (a.get_size() == b.get_size() and a.get_display_name() == b.get_display_name()
                and a.get_file_type() == b.get_file_type()
                and (a.get_modification_date_time() and a.get_modification_date_time().to_unix()) ==
                (b.get_modification_date_time() and b.get_modification_date_time().to_unix()))

    def _on_event(self, monitor, file, other, event):
        E = Gio.FileMonitorEvent
        if self.file is None or file.equal(self.file):
            return
        if event in (E.CREATED, E.MOVED_IN, E.CHANGES_DONE_HINT, E.ATTRIBUTE_CHANGED):
            self._upsert(file)
        elif event in (E.DELETED, E.MOVED_OUT):
            self._remove(file)
        elif event == E.RENAMED:
            self._remove(file)
            if other is not None:
                self._upsert(other)

    def _upsert(self, child):
        gen = self._gen

        def done(f, res):
            if gen != self._gen:
                return
            try:
                info = f.query_info_finish(res)
            except GLib.Error:  # it is already gone again (a short-lived file)
                self._remove(f)
                return
            info.set_attribute_object("standard::file", f)
            pos = self._find(f.get_basename())
            if pos is None:
                self.append(info)
            elif not self._same(self.get_item(pos), info):
                self.splice(pos, 1, [info])

        child.query_info_async(ATTRS, Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, None, done)

    def _remove(self, child):
        pos = self._find(child.get_basename())
        if pos is not None:
            self.remove(pos)

    # ---- double-checking
    def resync(self):
        """Compare the real folder with what is shown and fix any difference."""
        if self.file is None or self.props.loading or self._resyncing:
            return
        self._resyncing = True
        self._enumerate(self._gen, self.file, initial=False)

    def _poll_tick(self):
        self.resync()
        return True

    def _apply_diff(self, fresh):
        new = {i.get_name(): i for i in fresh}
        for pos in range(self.get_n_items() - 1, -1, -1):  # gone from disk
            if self.get_item(pos).get_name() not in new:
                self.remove(pos)
        have = {self.get_item(pos).get_name(): pos for pos in range(self.get_n_items())}
        for name, info in new.items():
            pos = have.get(name)
            if pos is None:
                self.append(info)
            elif not self._same(self.get_item(pos), info):
                self.splice(pos, 1, [info])


class FolderTab(Gtk.Box):
    def __init__(self, win, file):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self.container = None
        self.file = None
        self.history = []
        self.idx = -1
        self.query = ""

        self.dirlist = FolderModel()
        self.dirlist.connect("notify::error", self._on_error)
        self.dirlist.connect("notify::loading", lambda *a: self._refresh())

        self.filter = Gtk.CustomFilter.new(self._match, None)
        self.fmodel = Gtk.FilterListModel.new(self.dirlist, self.filter)

        # search inside subfolders: results replace the folder's contents while a search is shown
        self.results = Gio.ListStore.new(Gio.FileInfo)
        self.query_text = ""
        self.searching = False        # showing search results instead of the folder
        self.search_done = True
        self.search_scanned = 0
        self.search_capped = False
        self.pending_select = None    # name to select once the folder has loaded ("Show in Folder")
        self._in_load = False
        self._search_gen = 0
        self._search_cancel = None
        self._search_timer = None
        self._status_timer = None

        # list view (columns) -- its sorter drives the shared sort model
        self.cv = Gtk.ColumnView(enable_rubberband=True)
        self.cv.add_css_class("data-table")
        self.cols = {}
        self._add_col("name", "Name", "name", lambda i: GLib.utf8_collate_key_for_filename(i.get_display_name(), -1), expand=True)
        self._add_col("size", "Size", "size", lambda i: -1 if is_dir(i) else i.get_size(), width=90)
        self._add_col("modified", "Modified", "date", mtime, width=120)
        self._add_col("type", "Type", "type", lambda i: type_description(i).casefold(), width=170)
        self._add_col("location", "Location", "loc", lambda i: (i.get_attribute_string("roost::rel") or "").casefold(), width=220)
        self._cols_width = 0
        self.cols["location"].set_visible(False)  # only shown for search results
        self.cv.add_tick_callback(self._fit_columns)

        dirs_first = Gtk.CustomSorter.new(lambda a, b, _: (not is_dir(a)) - (not is_dir(b)), None)
        multi = Gtk.MultiSorter()
        multi.append(dirs_first)
        multi.append(self.cv.get_sorter())
        self.smodel = Gtk.SortListModel.new(self.fmodel, multi)
        self.sel = Gtk.MultiSelection.new(self.smodel)
        self.cv.set_model(self.sel)

        self.gv = Gtk.GridView(model=self.sel, factory=self._grid_factory(), enable_rubberband=True,
                               min_columns=2, max_columns=14)
        zoom = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        zoom.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)  # before the scrolled window scrolls
        zoom.connect("scroll", self._on_zoom_scroll)
        self.gv.add_controller(zoom)
        self._zoom_accum = 0.0
        for v in (self.cv, self.gv):
            v.connect("activate", lambda v, pos: self.activate(pos))
        self._attach_view_models()

        def scroller(child):
            return Gtk.ScrolledWindow(child=child, vexpand=True, hexpand=True)

        self.pane_title = Gtk.Label(xalign=0, visible=False, ellipsize=Pango.EllipsizeMode.MIDDLE,
                                    css_classes=["heading", "pane-title"])
        self.append(self.pane_title)
        claim = Gtk.GestureClick(button=0)
        claim.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        claim.connect("pressed", lambda *a: self._claim())
        self.add_controller(claim)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=140)
        self.stack.add_named(scroller(self.gv), "grid")
        self.stack.add_named(scroller(self.cv), "list")
        self.empty = Adw.StatusPage(icon_name="folder-symbolic", title="Folder is Empty")
        logo = LOGO
        if os.path.exists(logo):
            try:
                self.empty.set_paintable(Gdk.Texture.new_for_pixbuf(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(logo, 200, 120, True)))
            except GLib.Error:
                pass
        self.stack.add_named(self.empty, "empty")
        self.append(self.stack)

        self.status = Gtk.Label(xalign=0, css_classes=["status-bar"])
        self.append(self.status)
        # tiny anchor for context menus (GTK height-caps menus hung from wide widgets)
        self.menu_anchor = Gtk.Box(can_target=False, focusable=False)
        self.menu_anchor.set_size_request(1, 1)
        self.append(self.menu_anchor)

        click = Gtk.GestureClick(button=3)
        click.connect("pressed", self._on_bg_menu)
        self.stack.add_controller(click)
        dbl = Gtk.GestureClick(button=1)
        dbl.connect("pressed", self._on_bg_double_click)
        self.stack.add_controller(dbl)
        drop = Gtk.DropTarget.new(Gdk.FileList.__gtype__, DND_ACTIONS)
        drop.connect("drop", self._on_drop_view)
        self.stack.add_controller(drop)

        self.sel.connect("selection-changed", lambda *a: self._selection_changed())
        self.fmodel.connect("items-changed", lambda *a: self._refresh())

        self.sort_by(win.sort_key, win.sort_desc)
        self.navigate(file)

    # ---- columns / cells
    def _add_col(self, key, title, kind, keyfn, expand=False, width=None):
        f = Gtk.SignalListItemFactory()
        f.connect("setup", self._setup_cell, kind)
        f.connect("bind", self._bind_cell, kind)
        f.connect("unbind", self._unbind_cell, kind)
        col = Gtk.ColumnViewColumn.new(title, f)

        def cmp(a, b, _):
            ka, kb = keyfn(a), keyfn(b)
            return (ka > kb) - (ka < kb)

        col.set_sorter(Gtk.CustomSorter.new(cmp, None))
        col.set_expand(expand)
        col.set_resizable(True)
        if width:
            col.set_fixed_width(width)
        self.cv.append_column(col)
        self.cols[key] = col

    def sort_by(self, key, desc):
        self.cv.sort_by_column(self.cols[key], Gtk.SortType.DESCENDING if desc else Gtk.SortType.ASCENDING)

    def _setup_cell(self, factory, li, kind):
        if kind == "grid":
            size = self.win.icon_size
            cell = max(96, size + 40)
            w = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
            w.img = Gtk.Image(pixel_size=size)
            w.lbl = Gtk.Label(justify=Gtk.Justification.CENTER, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                              lines=2, ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=max(9, round(cell / 8.6)))
            w.set_size_request(cell, -1)
            w.append(w.img)
            w.append(w.lbl)
        elif kind == "name":
            w = Gtk.Box(spacing=10)
            w.img = Gtk.Image(pixel_size=20)
            w.lbl = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE)
            w.append(w.img)
            w.append(w.lbl)
        else:
            w = Gtk.Label(xalign=0, hexpand=True, css_classes=["dim-label"], ellipsize=Pango.EllipsizeMode.END)
        li.set_child(w)
        w._li = li  # lets the keyboard menu find out which item has focus
        self._attach_controllers(li, w)

    def _bind_cell(self, factory, li, kind):
        info, w = li.get_item(), li.get_child()
        if kind in ("grid", "name"):
            name = info.get_display_name()
            w.lbl.set_text(name)
            rel = info.get_attribute_string("roost::rel")
            w.set_tooltip_text(f"{name}\n{rel or 'in the searched folder'}" if rel is not None else name)
            w.set_opacity(0.55 if info.get_is_hidden() else 1.0)
            icon = info.get_icon()
            if icon is not None:
                w.img.set_from_gicon(icon)
            names = icon.get_names() if isinstance(icon, Gio.ThemedIcon) else []
            # plain folders go gray; picture icons (custom images, the Desktop wallpaper) keep their colours
            if is_dir(info) and not isinstance(icon, Gio.FileIcon) and not any(n.startswith("user-") for n in names):
                w.img.add_css_class("folder-icon")
            else:
                w.img.remove_css_class("folder-icon")
            if kind == "grid":
                apply_thumb(w.img, info)
        elif kind == "size":
            w.set_text("" if is_dir(info) else GLib.format_size(info.get_size()))
        elif kind == "date":
            w.set_text(fmt_date(info))
        elif kind == "type":
            w.set_text(type_description(info))
        elif kind == "loc":
            w.set_text(info.get_attribute_string("roost::rel") or "")

    def _unbind_cell(self, factory, li, kind):
        w = li.get_child()
        if kind in ("grid", "name"):
            w.img._token = None

    def _attach_controllers(self, li, w):
        click = Gtk.GestureClick(button=3)
        click.connect("pressed", self._on_item_menu, li)
        w.add_controller(click)

        # A press on an item must not start the view's rubber-band selection: that gesture claims the
        # mouse and cancels the drag. Switch it off while the button is down on an item, back on after.
        press = Gtk.GestureClick(button=1)
        press.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        press.connect("pressed", lambda *a: self._rubberband(False))
        press.connect("released", lambda *a: self._rubberband(True))
        press.connect("stopped", lambda *a: self._rubberband(True))
        w.add_controller(press)

        ds = Gtk.DragSource(actions=DND_ACTIONS)
        ds.connect("prepare", self._drag_prepare, li)
        ds.connect("drag-end", lambda *a: self._rubberband(True))
        ds.connect("drag-cancel", lambda *a: self._rubberband(True) or False)
        w.add_controller(ds)

        dt = Gtk.DropTarget.new(Gdk.FileList.__gtype__, DND_ACTIONS)
        dt.connect("accept", lambda t, drop, li=li: li.get_item() is not None and is_dir(li.get_item()))
        dt.connect("drop", self._on_drop_item, li)
        w.add_controller(dt)

    # ---- navigation
    def navigate(self, file, push=True):
        if push:
            del self.history[self.idx + 1:]
            self.history.append(file)
            self.idx = len(self.history) - 1
        self._load(file)

    def _load(self, file):
        self._in_load = True  # refreshes triggered while switching folders must not use up pending_select
        self.stop_search()
        self.file = file
        self.query = ""
        self.query_text = ""
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.dirlist.set_file(file)
        self.sel.unselect_all()
        self.empty.set_title("Trash is Empty" if file.get_uri_scheme() == "trash" else "Folder is Empty")
        self.refresh_title()
        self._in_load = False
        self._refresh()
        self.win.tab_location_changed(self)
        GLib.idle_add(self.focus_view)

    def refresh_title(self):
        if self.file is None:
            return
        name = display_name(self.file)
        self.pane_title.set_text(name)
        self.pane_title.set_tooltip_text(self.file.get_path() or self.file.get_uri())
        if self.container is not None and self.container.active is self:
            self.container.refresh_title()

    def _claim(self):
        if self.container is not None:
            self.container.set_active(self)

    def set_active_look(self, split, active):
        self.pane_title.set_visible(split)
        for c in ("pane-active", "pane-inactive"):
            self.remove_css_class(c)
        if split:
            self.add_css_class("pane-active" if active else "pane-inactive")

    def can_back(self):
        return self.idx > 0

    def can_forward(self):
        return self.idx < len(self.history) - 1

    def back(self):
        if self.can_back():
            self.idx -= 1
            self._load(self.history[self.idx])

    def forward(self):
        if self.can_forward():
            self.idx += 1
            self._load(self.history[self.idx])

    def up(self):
        parent = self.file.get_parent()
        if parent is not None:
            self.navigate(parent)

    def _on_error(self, dirlist, _pspec):
        err = dirlist.get_error()
        if err is None:
            return
        self.win.toast(f"Can't open folder: {err.message}")
        if self.idx > 0:
            del self.history[self.idx]
            self.idx -= 1
            GLib.idle_add(self._load, self.history[self.idx])

    # ---- model plumbing
    def _match(self, info, _data):
        if not self.win.show_hidden and (info.get_is_hidden() or info.get_is_backup()):
            return False
        if self.query and not self.searching:  # search results already match the query
            return self.query in info.get_display_name().casefold()
        return True

    def _grid_factory(self):
        gf = Gtk.SignalListItemFactory()
        gf.connect("setup", self._setup_cell, "grid")
        gf.connect("bind", self._bind_cell, "grid")
        gf.connect("unbind", self._unbind_cell, "grid")
        return gf

    def apply_zoom(self):
        self.gv.set_factory(self._grid_factory())  # new factory = every cell is rebuilt at the new size

    def _on_zoom_scroll(self, ctrl, dx, dy):
        if not ctrl.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            return False
        self._zoom_accum += dy
        if abs(self._zoom_accum) >= 1:
            self.win.zoom(-1 if self._zoom_accum > 0 else 1)  # scroll up = bigger icons
            self._zoom_accum = 0.0
        return True

    def _fit_columns(self, view, clock):
        width = view.get_width()
        if width and width != self._cols_width:
            self._cols_width = width
            self._apply_columns()
        return GLib.SOURCE_CONTINUE

    def _apply_columns(self):
        """Show only the columns that fit: in a narrow pane (split view) the fixed-width columns would
        squeeze the file names down to a few pixels."""
        width = self._cols_width or 10_000
        self.cols["type"].set_visible(width >= 700)
        self.cols["modified"].set_visible(width >= 420)
        self.cols["size"].set_visible(width >= 340)
        self.cols["location"].set_visible(self.searching and width >= 600)

    def _wants_deep_search(self, text):
        return bool(self.win.deep_search and text.strip() and self.file is not None and self.file.get_path())

    def set_query(self, text):
        deep = self._wants_deep_search(text)
        if text == self.query_text and deep == (self.searching or self._search_timer is not None):
            return  # nothing changed (e.g. the search box is just being synced after a tab switch)
        self.query_text = text
        self.query = text.casefold()
        if deep:
            self._schedule_search(text.strip())
        else:
            self.stop_search()
            self.filter.changed(Gtk.FilterChange.DIFFERENT)

    # ---- search inside subfolders
    def _schedule_search(self, text):
        if self._search_timer is not None:
            GLib.source_remove(self._search_timer)
        self._search_timer = GLib.timeout_add(250, self._begin_search, text)  # wait for a pause in typing

    def _begin_search(self, text):
        self._search_timer = None
        self.start_search(text)
        return False

    def start_search(self, text):
        self._cancel_search()
        self.searching, self.search_done, self.search_capped, self.search_scanned = True, False, False, 0
        self.results.remove_all()
        self.fmodel.set_model(self.results)
        self._apply_columns()
        self._search_gen += 1
        cancel = self._search_cancel = threading.Event()
        threading.Thread(target=self._search_worker, daemon=True,
                         args=(self._search_gen, self.file.get_path(), text, self.win.show_hidden, cancel)).start()
        if self._status_timer is None:
            self._status_timer = GLib.timeout_add(250, self._search_tick)
        self._refresh()

    def _cancel_search(self):
        if self._search_timer is not None:
            GLib.source_remove(self._search_timer)
            self._search_timer = None
        if self._search_cancel is not None:
            self._search_cancel.set()
            self._search_cancel = None
        self._search_gen += 1  # results still in flight from the old search are ignored

    def stop_search(self):
        self._cancel_search()
        if self.searching:
            self.searching = False
            self.search_done = True
            self.results.remove_all()
            self.fmodel.set_model(self.dirlist)
            self._apply_columns()
            self._refresh()

    def _search_tick(self):
        if self.searching and not self.search_done:
            self._selection_changed()
            return True
        self._status_timer = None
        return False

    def _search_worker(self, gen, root, text, show_hidden, cancel):
        """Walk the folder tree breadth-first (nearby results first), pushing matches to the UI in batches."""
        pattern = text.casefold()
        is_glob = any(c in pattern for c in "*?[")
        words = pattern.split()
        queue, batch, found, scanned = collections.deque([root]), [], 0, 0
        last = time.monotonic()
        capped = False

        def push(final=False):
            nonlocal batch, last
            GLib.idle_add(self._search_push, gen, batch, scanned, capped, final)
            batch, last = [], time.monotonic()

        seen_entries = 0
        while queue and not cancel.is_set() and not capped:
            folder = queue.popleft()
            try:
                it = os.scandir(folder)
            except OSError:
                continue
            scanned += 1
            self.search_scanned = scanned
            with it:  # stream the entries instead of building a huge list (less memory, fewer pauses)
                for entry in it:
                    if cancel.is_set():
                        break
                    seen_entries += 1
                    if seen_entries % 150 == 0:
                        time.sleep(0.0005)  # let the window draw: the UI thread shares the interpreter with us
                    name = entry.name
                    if not show_hidden and name.startswith("."):
                        continue
                    folded = name.casefold()
                    hit = fnmatch.fnmatchcase(folded, pattern) if is_glob else all(w in folded for w in words)
                    if hit:
                        info = self._result_info(entry.path, root)
                        if info is not None:
                            batch.append(info)
                            found += 1
                            if found >= SEARCH_LIMIT:
                                capped = True
                                break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            queue.append(entry.path)
                    except OSError:
                        pass
                    if batch and (len(batch) >= SEARCH_BATCH or time.monotonic() - last > 0.1):
                        push()
        if not cancel.is_set():
            push(final=True)

    @staticmethod
    def _result_info(path, root):
        f = Gio.File.new_for_path(path)
        try:
            info = f.query_info(ATTRS, NOFOLLOW, None)
        except GLib.Error:
            return None
        info.set_attribute_object("standard::file", f)
        rel = os.path.relpath(os.path.dirname(path), root)
        info.set_attribute_string("roost::rel", "" if rel == "." else rel)
        return info

    def _search_push(self, gen, batch, scanned, capped, final):
        if gen != self._search_gen or not self.searching:
            return False
        if batch:
            self.results.splice(self.results.get_n_items(), 0, batch)
        self.search_scanned, self.search_capped = scanned, capped
        if final or capped:
            self.search_done = True
        self._refresh()
        return False

    def set_view(self, mode):
        self.view_mode = mode
        self._attach_view_models()
        self._refresh()

    def _attach_view_models(self):
        """Only the view on screen gets the data. A view that has the model builds a widget for every
        row it can see, even when it is hidden, which doubled the work for every folder and search."""
        mode = getattr(self, "view_mode", self.win.view_mode)
        self.gv.set_model(self.sel if mode == "grid" else None)
        self.cv.set_model(self.sel if mode == "list" else None)

    def reveal(self, pos):
        """Scroll an item into view."""
        try:
            if getattr(self, "view_mode", "grid") == "grid":
                self.gv.scroll_to(pos, Gtk.ListScrollFlags.NONE, None)
            else:
                self.cv.scroll_to(pos, None, Gtk.ListScrollFlags.NONE, None)
        except (TypeError, AttributeError):
            pass

    def focus_view(self):
        (self.gv if getattr(self, "view_mode", "grid") == "grid" else self.cv).grab_focus()

    def _refresh(self):
        n = self.fmodel.get_n_items()
        mode = getattr(self, "view_mode", self.win.view_mode)
        if self.searching:
            if n == 0:
                self.empty.set_title("Searching…" if not self.search_done else "No Results")
                self.stack.set_visible_child_name("empty")
            else:
                self.stack.set_visible_child_name(mode)
        elif n == 0 and not self.dirlist.is_loading():
            self.empty.set_title("No Results" if self.query else self.empty.get_title())
            self.stack.set_visible_child_name("empty")
        else:
            self.stack.set_visible_child_name(mode)
        if self.pending_select and not self.searching and not self._in_load and not self.dirlist.is_loading():
            self._select_pending()
        self._selection_changed()

    def select_when_ready(self, name):
        self.pending_select = name
        self._pending_deadline = time.monotonic() + 4

    def _select_pending(self):
        name, self.pending_select = self.pending_select, None
        found = any(self.sel.get_item(p).get_display_name() == name or self.sel.get_item(p).get_name() == name
                    for p in range(self.sel.get_n_items()))
        if not found and time.monotonic() < getattr(self, "_pending_deadline", 0):
            self.pending_select = name  # not listed yet: try again at the next refresh
            return
        for pos in range(self.sel.get_n_items()):
            if self.sel.get_item(pos).get_display_name() == name or self.sel.get_item(pos).get_name() == name:
                self.sel.unselect_all()
                self.sel.select_item(pos, True)
                try:
                    if (getattr(self, "view_mode", "grid")) == "grid":
                        self.gv.scroll_to(pos, Gtk.ListScrollFlags.FOCUS, None)
                    else:
                        self.cv.scroll_to(pos, None, Gtk.ListScrollFlags.FOCUS, None)
                except (TypeError, AttributeError):
                    pass
                return

    def _selection_changed(self):
        bs = self.sel.get_selection()
        count = bs.get_size()
        if count == 0:
            n = self.fmodel.get_n_items()
            if self.searching and not self.search_done:
                text = f"Searching… {n} found · {self.search_scanned:,} folders checked"
            elif self.searching:
                text = f"{n} result{'s' if n != 1 else ''} for “{self.query_text}” in {self.search_scanned:,} folders"
                if self.search_capped:
                    text += f" · stopped at {SEARCH_LIMIT:,}, refine the search to narrow it down"
            else:
                text = f"{n} item{'s' if n != 1 else ''}"
                if self.query:
                    text += " match" + ("es" if n != 1 else "")
        else:
            total = sum(i.get_size() for i in self.selected_infos() if not is_dir(i))
            text = f"{count} selected" + (f" · {GLib.format_size(total)}" if total else "")
        self.status.set_text(text)
        self.win.update_actions()
        if self.container is not None and self.container.active is self:
            self.win.update_search_spinner()

    # ---- selection
    def selected_infos(self):
        bs = self.sel.get_selection()
        return [self.sel.get_item(bs.get_nth(i)) for i in range(bs.get_size())]

    def selected_files(self):
        return [info_file(i) for i in self.selected_infos()]

    def activate(self, pos):
        info = self.sel.get_item(pos)
        if is_dir(info):
            self.navigate(info_file(info))
        else:
            self.win.launch(info_file(info))

    # ---- menus / dnd
    def _on_item_menu(self, gesture, n, x, y, li):
        pos = li.get_position()
        if not self.sel.is_selected(pos):
            self.sel.select_item(pos, True)
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.win.popup(gesture.get_widget(), x, y, "trash" if self.file.get_uri_scheme() == "trash" else "item")

    def keyboard_menu(self, focus):
        """The Menu key (or Shift+F10): open the right-click menu for the selection, beside the focused item."""
        li = find_list_item(focus) if is_inside(focus, self.stack) else None
        if li is not None:
            pos = li.get_position()
            if pos != Gtk.INVALID_LIST_POSITION and not self.sel.is_selected(pos):
                self.sel.select_item(pos, True)  # like a right-click: the item you are on is the one acted on
        selected = self.sel.get_selection().get_size() > 0
        trash = self.file.get_uri_scheme() == "trash"
        kind = ("trash" if trash else "item") if selected else ("trash-bg" if trash else "bg")
        if li is not None and selected:
            self.win.popup(focus, focus.get_width() / 2, focus.get_height() / 2, kind)
        else:
            self.win.popup(self.stack, 60, 60, kind)

    def _on_bg_double_click(self, gesture, n, x, y):
        # only the view background counts, not items, column headers or scrollbars
        w = self.stack.pick(x, y, Gtk.PickFlags.DEFAULT)
        if w is None or w.get_css_name() not in ("gridview", "listview", "viewport", "scrolledwindow", "statuspage", "stack"):
            return
        if n == 1:
            mods = gesture.get_current_event_state() & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
            if not mods:
                self.sel.unselect_all()
        elif n == 2:
            self.up()

    def _on_bg_menu(self, gesture, n, x, y):
        self.sel.unselect_all()
        trash = self.file.get_uri_scheme() == "trash"
        self.win.popup(gesture.get_widget(), x, y, "trash-bg" if trash else "bg")

    def _rubberband(self, on):
        for view in (self.gv, self.cv):
            view.set_enable_rubberband(on)

    def _drag_prepare(self, source, x, y, li):
        pos = li.get_position()
        if not self.sel.is_selected(pos):
            self.sel.select_item(pos, True)
        files = self.selected_files()
        return Gdk.ContentProvider.new_for_value(files_value(files)) if files else None

    def _on_drop_item(self, target, value, x, y, li):
        info = li.get_item()
        if info is None or not is_dir(info):
            return False
        return self._drop(target, value, info_file(info))

    def _on_drop_view(self, target, value, x, y):
        return self._drop(target, value, self.file)

    def _drop(self, target, value, dest):
        files = value.get_files()
        ctrl = ctrl_held(target)
        return self.win.drop_files(files, dest, copy=ctrl)


def looks_like_text(path):
    """True if the start of the file is valid UTF-8 text (no NUL bytes)."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(4096)
    except OSError:
        return False
    if b"\0" in chunk:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(chunk, final=False)  # tolerates a cut-off last character
    except UnicodeDecodeError:
        return False
    return True


def find_list_item(widget):
    """The list item behind a widget (or one of its descendants), if it is a cell of the file view."""
    if widget is None:
        return None
    li = getattr(widget, "_li", None)
    if li is not None:
        return li
    child = widget.get_first_child()
    while child is not None:
        found = find_list_item(child)
        if found is not None:
            return found
        child = child.get_next_sibling()
    return None


def is_inside(widget, ancestor):
    while widget is not None:
        if widget is ancestor:
            return True
        widget = widget.get_parent()
    return False


def preview_kind(info, path):
    if is_dir(info):
        return "folder"
    ct = content_type(info)
    if ct.startswith("image/"):
        return "image"
    if ct == "application/pdf":
        return "pdf"
    if path and (ct.startswith("text/") or looks_like_text(path)):
        return "text"
    return "other"


class PreviewDialog(Adw.Dialog):
    """Quick look at a file: images, PDFs (first pages) and text. Left/Right step through the folder."""

    def __init__(self, win, tab, pos):
        super().__init__(content_width=1000, content_height=720, title="Preview")
        self.win, self.tab, self.pos = win, tab, pos
        self.kind, self.page, self.pages, self._gen = "other", 1, 1, 0
        self.file = None

        self.title = Adw.WindowTitle(title="", subtitle="")
        header = Adw.HeaderBar(title_widget=self.title)
        nav = Gtk.Box(css_classes=["linked"])
        self.prev_btn = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Previous file (←)")
        self.next_btn = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Next file (→)")
        self.prev_btn.connect("clicked", lambda *a: self.step(-1))
        self.next_btn.connect("clicked", lambda *a: self.step(1))
        nav.append(self.prev_btn)
        nav.append(self.next_btn)
        header.pack_start(nav)
        open_btn = Gtk.Button(label="Open", tooltip_text="Open with the default app (Enter)",
                              css_classes=["suggested-action"])
        open_btn.connect("clicked", lambda *a: self.open_file())
        header.pack_end(open_btn)

        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True, hexpand=True, vexpand=True,
                                   margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        self.text = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=16, right_margin=16, top_margin=12, bottom_margin=12)
        self.info = Adw.StatusPage()
        self.spinner = Gtk.Spinner(spinning=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                                   width_request=32, height_request=32)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.stack.add_named(self.picture, "image")
        self.stack.add_named(Gtk.ScrolledWindow(child=self.text), "text")
        self.stack.add_named(self.info, "info")
        self.stack.add_named(self.spinner, "loading")

        self.page_prev = Gtk.Button(icon_name="go-up-symbolic", css_classes=["flat"], tooltip_text="Previous page (Page Up)")
        self.page_next = Gtk.Button(icon_name="go-down-symbolic", css_classes=["flat"], tooltip_text="Next page (Page Down)")
        self.page_prev.connect("clicked", lambda *a: self.turn_page(-1))
        self.page_next.connect("clicked", lambda *a: self.turn_page(1))
        self.note = Gtk.Label(css_classes=["dim-label", "caption"])
        self.bar = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_bottom=6, visible=False)
        for w_ in (self.page_prev, self.note, self.page_next):
            self.bar.append(w_)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self.stack)
        body.append(self.bar)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(body)
        self.set_child(view)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.show_item(pos)

    # ---- keys and navigation
    def _on_key(self, ctrl, keyval, keycode, state):
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        if keyval in (Gdk.KEY_space, Gdk.KEY_Escape):
            self.close()
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Right) or (keyval in (Gdk.KEY_Up, Gdk.KEY_Down) and self.kind != "text"):
            self.step(-1 if keyval in (Gdk.KEY_Left, Gdk.KEY_Up) else 1)
        elif keyval == Gdk.KEY_Page_Down and self.kind == "pdf":
            self.turn_page(1)
        elif keyval == Gdk.KEY_Page_Up and self.kind == "pdf":
            self.turn_page(-1)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.open_file()
        else:
            return False
        return True

    def step(self, delta):
        pos = self.pos + delta
        if 0 <= pos < self.tab.sel.get_n_items():
            self.show_item(pos)

    def open_file(self):
        if self.file is not None:
            self.close()
            self.win.launch(self.file)

    def turn_page(self, delta):
        page = self.page + delta
        if self.kind == "pdf" and 1 <= page <= self.pages:
            self.page = page
            self._load_pdf()

    # ---- showing one item
    def show_item(self, pos):
        self._gen += 1
        self.pos = pos
        info = self.tab.sel.get_item(pos)
        self.file = info_file(info)
        path = self.file.get_path()
        total = self.tab.sel.get_n_items()
        size = "" if is_dir(info) else f"{GLib.format_size(info.get_size())} · "
        self.title.set_title(info.get_display_name())
        self.title.set_subtitle(f"{type_description(info)} · {size}{pos + 1} of {total}")
        self.prev_btn.set_sensitive(pos > 0)
        self.next_btn.set_sensitive(pos < total - 1)
        self.tab.sel.unselect_all()
        self.tab.sel.select_item(pos, True)
        self.tab.reveal(pos)
        self.kind, self.page, self.pages = preview_kind(info, path), 1, 1
        self.info_item = info
        self.bar.set_visible(False)
        self.stack.set_visible_child_name("loading")
        if self.kind == "image":
            self._start(self._read_image, path)
        elif self.kind == "pdf":
            self._load_pdf()
        elif self.kind == "text":
            self._start(self._read_text, path)
        elif self.kind == "folder":
            self._start(self._count_folder, path)
        else:
            thumb = info.get_attribute_byte_string("thumbnail::path")
            self._show_thumbnail_or_card(info, thumb)

    def _start(self, worker, *args):
        gen = self._gen
        threading.Thread(target=worker, args=(gen, *args), daemon=True).start()

    def _deliver(self, gen, fn, *args):
        def run():
            if gen == self._gen and self.get_mapped():
                fn(*args)
            return False
        GLib.idle_add(run)

    # ---- the different kinds
    def _read_image(self, gen, path):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, IMAGE_PREVIEW_MAX, IMAGE_PREVIEW_MAX, True)
            pb = pb.apply_embedded_orientation() or pb
        except GLib.Error:
            thumb = self.info_item.get_attribute_byte_string("thumbnail::path")
            self._deliver(gen, self._show_thumbnail_or_card, self.info_item, thumb)
            return
        self._deliver(gen, self._set_texture, Gdk.Texture.new_for_pixbuf(pb))

    def _set_texture(self, texture):
        self.picture.set_paintable(texture)
        self.stack.set_visible_child_name("image")

    def _show_thumbnail_or_card(self, info, thumb):
        if thumb:
            try:
                self._set_texture(Gdk.Texture.new_from_filename(thumb))
                return
            except GLib.Error:
                pass
        self._show_card(info)

    def _show_card(self, info, extra=None):
        icon = info.get_icon()
        names = icon.get_names() if isinstance(icon, Gio.ThemedIcon) else []
        self.info.set_icon_name(next((n for n in names if Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).has_icon(n)),
                                     "text-x-generic-symbolic"))
        self.info.set_title(info.get_display_name())
        when = info.get_modification_date_time()
        bits = [type_description(info)]
        if not is_dir(info):
            bits.append(GLib.format_size(info.get_size()))
        if when:
            bits.append("modified " + when.to_local().format("%-d %b %Y, %H:%M"))
        self.info.set_description(extra or " · ".join(bits) + "\n\nNo preview is available for this type of file.")
        self.stack.set_visible_child_name("info")

    def _count_folder(self, gen, path):
        try:
            with os.scandir(path) as it:
                n = sum(1 for _ in it)
        except OSError:
            n = None
        text = "Could not read this folder." if n is None else f"Folder with {n:,} item{'s' if n != 1 else ''}."
        self._deliver(gen, self._show_card, self.info_item, text)

    def _read_text(self, gen, path):
        try:
            with open(path, "rb") as f:
                raw = f.read(TEXT_PREVIEW_LIMIT + 1)
        except OSError:
            self._deliver(gen, self._show_card, self.info_item, "Could not read this file.")
            return
        truncated = len(raw) > TEXT_PREVIEW_LIMIT
        text = raw[:TEXT_PREVIEW_LIMIT].decode("utf-8", errors="replace")
        self._deliver(gen, self._set_text, text, truncated)

    def _set_text(self, text, truncated):
        self.text.get_buffer().set_text(text)
        self.stack.set_visible_child_name("text")
        self.bar.set_visible(truncated)
        self.page_prev.set_visible(False)
        self.page_next.set_visible(False)
        self.note.set_text(f"Showing the first {TEXT_PREVIEW_LIMIT // 1000} KB")

    def _load_pdf(self):
        self.stack.set_visible_child_name("loading")
        self._start(self._render_pdf, self.file.get_path(), self.page)

    def _render_pdf(self, gen, path, page):
        if not shutil.which("pdftoppm"):
            self._deliver(gen, self._show_card, self.info_item,
                          "PDF previews need the poppler tools. Install the “poppler-utils” package.")
            return
        pages = self.pages
        if page == 1:
            try:
                out = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=15).stdout
                pages = next((int(l.split()[1]) for l in out.splitlines() if l.startswith("Pages:")), 1)
            except (OSError, subprocess.SubprocessError, ValueError):
                pages = 1
        tmp = tempfile.mkdtemp(prefix="roost-preview-")
        try:
            subprocess.run(["pdftoppm", "-png", "-r", "110", "-f", str(page), "-l", str(page), "-singlefile",
                            path, os.path.join(tmp, "page")], capture_output=True, timeout=40, check=True)
            texture = Gdk.Texture.new_from_filename(os.path.join(tmp, "page.png"))
        except (OSError, subprocess.SubprocessError, GLib.Error):
            self._deliver(gen, self._show_card, self.info_item, "This PDF could not be shown (it may be password protected).")
            return
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self._deliver(gen, self._set_pdf_page, texture, pages)

    def _set_pdf_page(self, texture, pages):
        self.pages = pages
        self._set_texture(texture)
        self.bar.set_visible(pages > 1)
        self.page_prev.set_visible(True)
        self.page_next.set_visible(True)
        self.page_prev.set_sensitive(self.page > 1)
        self.page_next.set_sensitive(self.page < pages)
        self.note.set_text(f"Page {self.page} of {pages}")


class _WlMessage(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("signature", ctypes.c_char_p), ("types", ctypes.POINTER(ctypes.c_void_p))]


class _WlInterface(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("version", ctypes.c_int), ("method_count", ctypes.c_int),
                ("methods", ctypes.POINTER(_WlMessage)), ("event_count", ctypes.c_int),
                ("events", ctypes.POINTER(_WlMessage))]


class WaylandBlur:
    """Asks the desktop to blur whatever is behind a window ("frosted glass").

    GTK has no API for this, so it speaks the Wayland ext-background-effect protocol directly. KDE Plasma 6
    supports it. Everywhere else (other compositors, X11) this quietly does nothing, so the app just stays
    translucent without the blur. Mistakes here cannot be caught in Python (the compositor drops the whole
    connection), so the rules are strict: one effect per window surface, and it is released before the surface
    goes away."""

    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.ok = False
        self._effects = {}  # wl_surface address -> effect proxy
        self._keep = []     # ctypes objects that must outlive the calls into libwayland
        try:
            self._connect()
        except Exception:  # noqa: BLE001 - anything unexpected just means "no blur here"
            self.ok = False

    def _interface(self, name, methods, events):
        def messages(items):
            arr = (_WlMessage * max(1, len(items)))()
            for i, (n, sig, types) in enumerate(items):
                t = (ctypes.c_void_p * max(1, len(types)))(*[ctypes.addressof(x) if x is not None else None for x in types])
                self._keep.append(t)
                arr[i] = _WlMessage(n.encode(), sig.encode(), ctypes.cast(t, ctypes.POINTER(ctypes.c_void_p)))
            self._keep.append(arr)
            return arr
        m, e = messages(methods), messages(events)
        iface = _WlInterface(name.encode(), 1, len(methods), ctypes.cast(m, ctypes.POINTER(_WlMessage)),
                             len(events), ctypes.cast(e, ctypes.POINTER(_WlMessage)))
        self._keep.append(iface)
        return iface

    def _connect(self):
        gi.require_version("GdkWayland", "4.0")
        from gi.repository import GdkWayland
        gdk_display = Gdk.Display.get_default()
        if not isinstance(gdk_display, GdkWayland.WaylandDisplay):
            return
        lib = ctypes.CDLL(ctypes.util.find_library("wayland-client"))
        gtk = ctypes.CDLL("libgtk-4.so.1")
        if not hasattr(lib, "wl_proxy_marshal_flags"):
            return
        self.lib, self.gtk = lib, gtk
        P, U32 = ctypes.c_void_p, ctypes.c_uint32
        lib.wl_proxy_marshal_flags.restype = ctypes.c_void_p
        lib.wl_display_create_queue.restype = ctypes.c_void_p
        lib.wl_proxy_create_wrapper.restype = ctypes.c_void_p
        lib.wl_proxy_get_version.restype = ctypes.c_uint32
        gtk.gdk_wayland_display_get_wl_display.restype = ctypes.c_void_p
        gtk.gdk_wayland_display_get_wl_display.argtypes = [ctypes.c_void_p]
        gtk.gdk_wayland_surface_get_wl_surface.restype = ctypes.c_void_p
        gtk.gdk_wayland_surface_get_wl_surface.argtypes = [ctypes.c_void_p]

        wl_registry = _WlInterface.in_dll(lib, "wl_registry_interface")
        wl_surface = _WlInterface.in_dll(lib, "wl_surface_interface")
        wl_region = _WlInterface.in_dll(lib, "wl_region_interface")
        wl_compositor = _WlInterface.in_dll(lib, "wl_compositor_interface")
        self.effect_if = self._interface("ext_background_effect_v1",
                                         [("destroy", "", []), ("set_blur_region", "?o", [wl_region])], [])
        manager_if = self._interface("ext_background_effect_manager_v1",
                                     [("destroy", "", []), ("get_background_effect", "no", [self.effect_if, wl_surface])],
                                     [("capabilities", "u", [None])])
        self.region_if = wl_region
        # use a private event queue so we never disturb GTK's own handling of the connection
        self.display = P(gtk.gdk_wayland_display_get_wl_display(ctypes.c_void_p(hash(gdk_display))))
        queue = P(lib.wl_display_create_queue(self.display))
        wrapper = P(lib.wl_proxy_create_wrapper(self.display))
        lib.wl_proxy_set_queue(wrapper, queue)
        registry = P(lib.wl_proxy_marshal_flags(wrapper, U32(1), P(ctypes.addressof(wl_registry)), U32(1), U32(0), P(None)))
        lib.wl_proxy_wrapper_destroy(wrapper)

        found = {}
        GLOBAL = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32)
        REMOVE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)
        callbacks = (GLOBAL(lambda data, reg, name, iface, ver: found.__setitem__(iface.decode(), (name, ver))),
                     REMOVE(lambda *a: None))
        listener = (ctypes.c_void_p * 2)(*[ctypes.cast(c, ctypes.c_void_p) for c in callbacks])
        self._keep += [callbacks, listener]
        lib.wl_proxy_add_listener(registry, listener, P(None))
        lib.wl_display_roundtrip_queue(self.display, queue)
        if "ext_background_effect_manager_v1" not in found or "wl_compositor" not in found:
            return

        def bind(iface, name, version):
            return P(lib.wl_proxy_marshal_flags(registry, U32(0), P(ctypes.addressof(iface)), U32(version), U32(0),
                                                U32(name), ctypes.c_char_p(iface.name), U32(version), P(None)))
        self.manager = bind(manager_if, found["ext_background_effect_manager_v1"][0], 1)
        self.compositor = bind(wl_compositor, found["wl_compositor"][0], min(4, found["wl_compositor"][1]))
        caps = []
        CAPS = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)
        cap_cb = CAPS(lambda data, proxy, flags: caps.append(flags))
        cap_listener = (ctypes.c_void_p * 1)(ctypes.cast(cap_cb, ctypes.c_void_p))
        self._keep += [cap_cb, cap_listener]
        lib.wl_proxy_add_listener(self.manager, cap_listener, P(None))
        lib.wl_display_roundtrip_queue(self.display, queue)
        self.ok = bool(caps and caps[0] & 1)  # bit 1 = the compositor can blur

    # ---- per window
    def _surface(self, window):
        surface = window.get_surface()
        if surface is None or "Wayland" not in type(surface).__name__:
            return None
        return self.gtk.gdk_wayland_surface_get_wl_surface(ctypes.c_void_p(hash(surface)))

    def _set_region(self, effect, on, shape=None):
        P, U32, I32 = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32
        lib = self.lib
        region = P(None)
        if on:  # the whole window (the compositor clips an oversized region to the window)
            region = P(lib.wl_proxy_marshal_flags(self.compositor, U32(1), P(ctypes.addressof(self.region_if)),
                                                  U32(lib.wl_proxy_get_version(self.compositor)), U32(0), P(None)))
            def add(x, y, w, h):
                lib.wl_proxy_marshal_flags(region, U32(1), P(None), U32(lib.wl_proxy_get_version(region)), U32(0),
                                           I32(x), I32(y), I32(w), I32(h))
            if shape is None:
                add(0, 0, 32767, 32767)
            else:  # a rounded rectangle, built from one-pixel strips (regions only know rectangles)
                x, y, w, h, r = shape
                r = min(r, w // 2, h // 2)
                for i in range(r):
                    inset = r - int(round((r * r - (r - i - 0.5) ** 2) ** 0.5))
                    add(x + inset, y + i, w - 2 * inset, 1)
                    add(x + inset, y + h - 1 - i, w - 2 * inset, 1)
                add(x, y + r, w, h - 2 * r)
        lib.wl_proxy_marshal_flags(effect, U32(1), P(None), U32(1), U32(0), region)
        if on:
            lib.wl_proxy_marshal_flags(region, U32(0), P(None), U32(lib.wl_proxy_get_version(region)), U32(1))
        lib.wl_display_flush(self.display)

    def set(self, window, on, shape=None):
        """Turn the blur behind this window on or off. Safe to call any time; does nothing if unsupported.
        `shape` (x, y, w, h, radius) limits it to a rounded rectangle instead of the whole surface."""
        if not self.ok:
            return
        try:
            surface = self._surface(window)
            if not surface:
                return
            effect = self._effects.get(surface)
            if effect is None:
                if not on:
                    return
                P, U32 = ctypes.c_void_p, ctypes.c_uint32
                effect = P(self.lib.wl_proxy_marshal_flags(self.manager, U32(1), P(ctypes.addressof(self.effect_if)), U32(1),
                                                           U32(0), P(None), P(surface)))
                self._effects[surface] = effect
            self._set_region(effect, on, shape)
            window.queue_draw()  # the change takes effect with the window's next frame
        except Exception:  # noqa: BLE001
            pass

    def release(self, window):
        """Must run before the window's surface is destroyed: a leftover effect would be a fatal protocol error."""
        if not self.ok:
            return
        try:
            surface = self._surface(window)
            effect = self._effects.pop(surface, None) if surface else None
            if effect is not None:
                P, U32 = ctypes.c_void_p, ctypes.c_uint32
                self.lib.wl_proxy_marshal_flags(effect, U32(0), P(None), U32(1), U32(1))  # destroy
                self.lib.wl_display_flush(self.display)
        except Exception:  # noqa: BLE001
            pass

    def error(self):
        """0 while the connection to the compositor is healthy (used by the tests)."""
        return self.lib.wl_display_get_error(self.display) if self.ok else 0


class MenuStyle:
    """Right-click and drop-down menus follow the system's menu transparency (KDE: System Settings > Breeze >
    Transparency) the way Dolphin's do, and get the same frosted blur behind them."""

    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.opacity = 1.0
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.path = os.path.join(GLib.get_user_config_dir(), "breezerc")
        self.reload()
        try:
            self.monitor = Gio.File.new_for_path(self.path).monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect("changed", lambda *a: GLib.timeout_add(200, lambda: (self.reload(), False)[1]))
        except GLib.Error:
            self.monitor = None

    def reload(self):
        opacity = 100
        kf = GLib.KeyFile()
        try:
            kf.load_from_file(self.path, GLib.KeyFileFlags.NONE)
            opacity = kf.get_integer("Style", "MenuOpacity")
        except GLib.Error:
            pass
        self.opacity = max(0.0, min(1.0, opacity / 100))
        if self.opacity >= 1.0:
            self.provider.load_from_string("")
        else:
            self.provider.load_from_string(f"popover {{ --popover-bg-color: rgba(22, 22, 26, {self.opacity:.2f}); }}")

    def attach(self, pop):
        """Blur behind this menu while it is open (only when the system asks for transparent menus)."""
        def shape_blur(p):
            # the popup's surface is bigger than the visible menu (it holds the shadow), so blur only the
            # rounded menu itself; otherwise the blur shows as square corners around it
            child = p.get_first_child()
            while child is not None and child.get_css_name() != "contents":
                child = child.get_next_sibling()
            ok, bounds = child.compute_bounds(p) if child is not None else (False, None)
            if not ok or not p.get_mapped():
                return False
            dx, dy = p.get_surface_transform()
            WaylandBlur.get().set(p, True, (int(dx + bounds.get_x()), int(dy + bounds.get_y()),
                                            int(bounds.get_width()), int(bounds.get_height()), 12))
            return False

        pop.connect("map", lambda p: self.opacity < 1.0 and GLib.idle_add(shape_blur, p))
        pop.connect("closed", lambda p: WaylandBlur.get().release(p))


class TabContainer(Gtk.Box):
    """One browser tab: a single folder pane, or two panes side by side."""

    def __init__(self, win, pane):
        super().__init__(hexpand=True, vexpand=True)
        self.win = win
        self.page = None
        self.panes = [pane]
        self.active = pane
        self.paned = None
        pane.container = self
        pane.set_hexpand(True)
        self.append(pane)

    def other(self):
        return next((p for p in self.panes if p is not self.active), None)

    def refresh_title(self):
        if self.page is not None:
            self.page.set_title(display_name(self.active.file))

    def set_active(self, pane):
        if pane is self.active:
            return
        self.active = pane
        self._mark()
        self.refresh_title()
        self.win.active_changed(self)

    def _mark(self):
        split = len(self.panes) > 1
        for p in self.panes:
            p.set_active_look(split, p is self.active)

    def toggle_split(self):
        if len(self.panes) == 1:
            first = self.panes[0]
            second = FolderTab(self.win, first.file)
            second.container = self
            second.set_hexpand(True)
            second.set_view(self.win.view_mode)
            self.remove(first)
            self.paned = Gtk.Paned(start_child=first, end_child=second, hexpand=True, vexpand=True,
                                   resize_start_child=True, resize_end_child=True,
                                   shrink_start_child=False, shrink_end_child=False)
            self.append(self.paned)
            self.panes = [first, second]
            GLib.idle_add(lambda: self.paned.set_position(max(250, self.get_width() // 2)) and False)
        else:
            keep = self.active
            for p in self.panes:
                if p is not keep:
                    p.set_active_look(False, False)
            self.paned.set_start_child(None)
            self.paned.set_end_child(None)
            self.remove(self.paned)
            self.paned = None
            self.panes = [keep]
            self.append(keep)
        self._mark()
        self.refresh_title()
        self.win.active_changed(self)


# ------------------------------------------------------------------ window
class Window(Adw.ApplicationWindow):
    def __init__(self, app, start, restore=False, empty=False, primary=True):
        cfg = load_config()
        win = cfg.get("window") if isinstance(cfg.get("window"), dict) else {}
        super().__init__(application=app, default_width=max(500, as_int(win.get("width"), 1120)),
                         default_height=max(350, as_int(win.get("height"), 720)), title="Roost Xplorer")
        if win.get("maximized"):
            self.maximize()
        self.show_hidden = bool(cfg.get("show_hidden", False))
        self.deep_search = bool(cfg.get("search_deep", True))
        self.translucent = bool(cfg.get("translucent", True))
        saved = as_int(cfg.get("icon_size"), 72)
        self.icon_size = min(ZOOM_STEPS, key=lambda z: abs(z - saved))
        self.compress_format = cfg.get("compress_format") if cfg.get("compress_format") in ARCHIVE_FORMATS else "zip"
        self.view_mode = cfg.get("view", "grid") if cfg.get("view") in ("grid", "list") else "grid"
        sort = cfg.get("sort") if isinstance(cfg.get("sort"), dict) else {}
        self.sort_key = sort.get("key", "name") if sort.get("key") in ("name", "modified", "size", "type") else "name"
        self.sort_desc = bool(sort.get("desc", False))
        self._session_timer = None
        # only the first window remembers the open tabs: extra windows (pulled-out tabs, new windows) must not
        # overwrite them
        self.save_session = primary and not empty
        self._menu_page = None
        self.cut_files = []
        self._menu_height = {}
        self.jobs = []
        labels, favs = cfg.get("labels"), cfg.get("favorites")
        self.labels = {k: v for k, v in labels.items() if isinstance(v, str)} if isinstance(labels, dict) else {}
        self.favorites = [u for u in favs if isinstance(u, str)] if isinstance(favs, list) else []
        self._ctx_row = None
        self.job_rows = {}
        self.undo_stack = []
        self._last_toast = None
        self.acts = {}
        self.vm = Gio.VolumeMonitor.get()

        self._build_ui()
        self._build_actions(app)
        self._build_menus()
        self.rebuild_sidebar()
        for sig in ("mount-added", "mount-removed", "mount-changed", "volume-added", "volume-removed"):
            self.vm.connect(sig, lambda *a: self.rebuild_sidebar())
        GLib.timeout_add_seconds(30, self._usage_tick)
        # make the menus and buttons reflect the remembered settings
        self.lookup_action("show-hidden").set_state(GLib.Variant("b", self.show_hidden))
        self.lookup_action("sort").set_state(GLib.Variant("s", self.sort_key))
        self.lookup_action("sort-desc").set_state(GLib.Variant("b", self.sort_desc))
        self.sidebar_btn.set_active(bool(cfg.get("sidebar_visible", True)))
        self.update_view_button()
        self.apply_look()
        self.connect("notify::is-active", lambda *a: self.is_active() and self.resync_folders())
        self.connect("map", lambda *a: WaylandBlur.get().set(self, self.translucent))
        self.connect("unmap", lambda *a: WaylandBlur.get().release(self))  # before the surface is destroyed
        if empty:
            pass  # a tab is about to be moved in
        elif restore:
            self._restore_session(start)
        else:
            self.new_tab(start)

    # ---- remembering settings and open tabs
    def _usable_dir(self, uri):
        try:
            f = Gio.File.new_for_uri(uri)
            return f if f.query_exists(None) and file_is_dir(f) else None
        except GLib.Error:
            return None

    def _restore_session(self, fallback):
        sess = load_config().get("session")
        sess = sess if isinstance(sess, dict) else {}
        saved_selected = as_int(sess.get("selected"), 0)
        target_page = None
        specs = sess.get("tabs") if isinstance(sess.get("tabs"), list) else []
        for n, spec in enumerate(specs):
            if not isinstance(spec, dict) or not isinstance(spec.get("panes"), list):
                continue
            dirs = [d for d in (self._usable_dir(u) for u in spec["panes"] if isinstance(u, str)) if d is not None][:2]
            if not dirs:
                continue
            self.new_tab(dirs[0])
            cont = self.container()
            if len(dirs) == 2:
                cont.toggle_split()
                cont.panes[1].navigate(dirs[1])
                cont.set_active(cont.panes[min(max(as_int(spec.get("active"), 0), 0), 1)])
            if n == saved_selected:
                target_page = cont.page
        if self.tabview.get_n_pages() == 0:
            self.new_tab(fallback)
        elif target_page is not None:
            self.tabview.set_selected_page(target_page)

    def session_state(self):
        tabs = []
        for i in range(self.tabview.get_n_pages()):
            cont = self.tabview.get_nth_page(i).get_child()
            tabs.append({"panes": [p.file.get_uri() for p in cont.panes], "active": cont.panes.index(cont.active)})
        page = self.tabview.get_selected_page()
        return {"tabs": tabs, "selected": self.tabview.get_page_position(page) if page else 0}

    def schedule_session_save(self):
        """Save the open tabs a moment after the last change, so a crash or kill doesn't lose them."""
        if not self.save_session:
            return
        if self._session_timer is not None:
            GLib.source_remove(self._session_timer)
        self._session_timer = GLib.timeout_add(800, self._save_session_now)

    def _save_session_now(self):
        self._session_timer = None
        if self.tabview.get_n_pages() > 0:
            save_config({"session": self.session_state()})
        return False

    def save_prefs(self):
        save_config({"view": self.view_mode, "show_hidden": self.show_hidden, "search_deep": self.deep_search, "compress_format": self.compress_format, "icon_size": self.icon_size,
                     "translucent": self.translucent,
                     "sort": {"key": self.sort_key, "desc": self.sort_desc}})

    # ---- UI construction
    def _build_ui(self):
        keys = Gtk.EventControllerKey()  # added first so Space reaches us before the search bar's type-to-search
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_window_key)
        self.add_controller(keys)

        self.tabview = Adw.TabView()
        self.tabview.connect("notify::selected-page", lambda *a: self._on_tab_changed())
        self.tabview.connect("notify::n-pages", self._on_pages_changed)
        self.tabview.connect("create-window", self._on_create_window)   # a tab was dragged out of the tab bar
        self.tabview.connect("page-attached", self._on_page_attached)   # a tab arrived (new, or from another window)
        self.tabview.connect("setup-menu", self._on_tab_menu)
        tab_menu = Gio.Menu()
        tab_menu.append("Move to New Window", "win.tab-new-window")
        tab_menu.append("Duplicate Tab", "win.tab-duplicate")
        tab_menu.append("Close Other Tabs", "win.tab-close-others")
        tab_menu.append("Close Tab", "win.tab-close")
        self.tabview.set_menu_model(tab_menu)
        self.tabbar = Adw.TabBar(view=self.tabview, autohide=True)
        newtab = Gtk.Button(icon_name="tab-new-symbolic", css_classes=["flat"], tooltip_text="New Tab (Ctrl+T)")
        newtab.connect("clicked", lambda *a: self.new_tab(self.tab().file))
        self.tabbar.set_end_action_widget(newtab)

        # header
        header = Adw.HeaderBar(show_start_title_buttons=False)
        self.sidebar_btn = Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Sidebar (F9)", active=True)
        header.pack_start(self.sidebar_btn)
        nav = Gtk.Box(css_classes=["linked"])
        self.back_btn = Gtk.Button(icon_name="go-previous-symbolic", action_name="win.back", tooltip_text="Back (Alt+←)")
        self.fwd_btn = Gtk.Button(icon_name="go-next-symbolic", action_name="win.forward", tooltip_text="Forward (Alt+→)")
        nav.append(self.back_btn)
        nav.append(self.fwd_btn)
        header.pack_start(nav)

        self.crumbs = Gtk.Box(spacing=0, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        self.crumb_scroll = Gtk.ScrolledWindow(child=self.crumbs, hexpand=True, vscrollbar_policy=Gtk.PolicyType.NEVER,
                                               hscrollbar_policy=Gtk.PolicyType.EXTERNAL)
        edit = Gtk.GestureClick(button=1)
        edit.connect("released", lambda *a: self.focus_location())
        self.crumb_scroll.add_controller(edit)
        self.loc_entry = Gtk.Entry(hexpand=True, placeholder_text="Enter a path or URL")
        self.loc_entry.connect("activate", lambda e: self.open_location(e.get_text()))
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._loc_key)
        self.loc_entry.add_controller(keys)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *a: self.loc_stack.set_visible_child_name("crumbs"))
        self.loc_entry.add_controller(focus)
        self.loc_stack = Gtk.Stack()
        self.loc_stack.add_named(self.crumb_scroll, "crumbs")
        self.loc_stack.add_named(self.loc_entry, "entry")
        header.set_title_widget(Adw.Clamp(child=self.loc_stack, maximum_size=760, tightening_threshold=600))

        self.menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", primary=True, tooltip_text="Main Menu")
        header.pack_end(self.menu_btn)
        self.view_btn = Gtk.Button(action_name="win.toggle-view", tooltip_text="Switch View")
        header.pack_end(self.view_btn)
        self.restore_btn = Gtk.Button(label="Restore", action_name="win.restore", visible=False)
        self.trash_btn = Gtk.Button(label="Empty Trash", action_name="win.empty-trash", visible=False,
                                    css_classes=["destructive-action"])
        header.pack_end(Gtk.Button(icon_name="view-dual-symbolic", action_name="win.toggle-split",
                                   tooltip_text="Split View (F3)"))
        header.pack_end(self.trash_btn)
        header.pack_end(self.restore_btn)

        # progress of running file operations
        self.ops_label = Gtk.Label(label="0%")
        ops_content = Gtk.Box(spacing=6)
        self.ops_bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
        self.ops_bar.set_size_request(90, -1)
        ops_content.append(self.ops_bar)
        ops_content.append(self.ops_label)
        self.ops_btn = Gtk.MenuButton(child=ops_content, visible=False, tooltip_text="File operations")
        self.ops_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=12, margin_bottom=12,
                                margin_start=12, margin_end=12)
        self.ops_list.set_size_request(320, -1)
        self.ops_btn.set_popover(Gtk.Popover(child=self.ops_list))
        header.pack_end(self.ops_btn)
        self.search_btn = Gtk.ToggleButton(icon_name="system-search-symbolic", tooltip_text="Search (Ctrl+F)")
        header.pack_end(self.search_btn)

        # search bar
        self.search_entry = Gtk.SearchEntry(hexpand=True)
        self.search_entry.connect("search-changed", lambda e: self.tab() and self.tab().set_query(e.get_text()))
        self.search_entry.connect("activate", lambda *a: self.tab().focus_view())
        self.deep_btn = Gtk.ToggleButton(label="Subfolders", active=self.deep_search,
                                         tooltip_text="Also search inside the folders below this one")
        self.deep_btn.connect("toggled", self._on_deep_toggled)
        self.search_spinner = Gtk.Spinner(visible=False)
        search_row = Gtk.Box(spacing=8)
        for w_ in (self.search_entry, self.search_spinner, self.deep_btn):
            search_row.append(w_)
        self._update_search_placeholder()
        self.searchbar = Gtk.SearchBar(child=Adw.Clamp(child=search_row, maximum_size=620))
        self.searchbar.connect_entry(self.search_entry)
        self.searchbar.set_key_capture_widget(self)
        self.searchbar.connect("notify::search-mode-enabled", self._on_search_mode)
        self.search_btn.bind_property("active", self.searchbar, "search-mode-enabled",
                                      GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)

        content = Adw.ToolbarView()
        content.add_top_bar(header)
        self.toasts = Adw.ToastOverlay(child=self.tabview, vexpand=True)
        # tab bar and search bar live in the content, not in the top-bar group: sharing the group
        # pads the header bar by a few pixels and keeps the window buttons off the top edge
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self.tabbar)
        body.append(self.searchbar)
        body.append(self.toasts)
        content.set_content(body)

        # sidebar
        self.side_list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.side_list.set_header_func(self._side_header)
        self.side_list.connect("row-activated", self._on_side_activated)
        # Drops are handled by the list itself, which works out the row under the pointer. (Drop targets
        # on the individual rows never receive the drag.)
        # One drop target takes both kinds of drag: files (move/copy them, or add folders as favorites) and a
        # favorite being dragged to a new place. (Two separate targets on the list fought over the drop.)
        drop = Gtk.DropTarget.new(Gdk.FileList.__gtype__, DND_ACTIONS)
        drop.set_gtypes([Gdk.FileList.__gtype__, GObject.TYPE_STRING])
        drop.set_preload(True)  # so we can look at what is being dragged while it hovers
        drop.connect("motion", self._side_motion)
        drop.connect("leave", lambda *a: (self._side_drop_highlight(None), self._fav_mark(None, False)))
        drop.connect("drop", self._side_drop_any)
        self.side_list.add_controller(drop)
        self._drop_row = None
        self._drop_header = None
        self._fav_mark_row = None
        side = Adw.ToolbarView()
        brand = Gtk.Box(spacing=8)
        logo = LOGO
        if os.path.exists(logo):
            brand.append(Gtk.Image(file=logo, pixel_size=34))
        brand.append(Gtk.Label(label="ROOST", css_classes=["brand-title"]))
        side.add_top_bar(Adw.HeaderBar(title_widget=brand, show_start_title_buttons=False,
                                         show_end_title_buttons=False))
        side.set_content(Gtk.ScrolledWindow(child=self.side_list, hscrollbar_policy=Gtk.PolicyType.NEVER))

        side.set_size_request(170, -1)
        self.split = Gtk.Paned(start_child=side, end_child=content, resize_start_child=False,
                               shrink_start_child=False, shrink_end_child=False,
                               position=load_config().get("sidebar_width", 240))
        self.sidebar_btn.bind_property("active", side, "visible",
                                       GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        self.connect("close-request", self._save_config)
        self.set_content(self.split)

    def _save_config(self, *a):
        if not self.save_session:
            return False
        data = {"sidebar_visible": self.sidebar_btn.get_active()}
        if self.sidebar_btn.get_active():
            data["sidebar_width"] = self.split.get_position()
        win = {"maximized": self.is_maximized()}
        if not (self.is_maximized() or self.is_fullscreen()):  # keep the last normal size while maximized
            win.update(width=self.get_width(), height=self.get_height())
        else:
            old = load_config().get("window", {})
            win.update({k: old[k] for k in ("width", "height") if k in old})
        data["window"] = win
        if self.tabview.get_n_pages() > 0:  # closing the last tab keeps the previous session
            data["session"] = self.session_state()
        save_config(data)
        return False

    def _build_actions(self, app):
        def add(name, cb, accels=None):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda *_: cb())
            self.add_action(a)
            self.acts[name] = a
            if accels:
                app.set_accels_for_action(f"win.{name}", accels)

        add("back", lambda: self.tab().back(), ["<Alt>Left"])
        add("forward", lambda: self.tab().forward(), ["<Alt>Right"])
        add("up", lambda: self.tab().up(), ["<Alt>Up", "BackSpace"])
        add("home", lambda: self.go(Gio.File.new_for_path(GLib.get_home_dir())), ["<Alt>Home"])
        add("location", self.focus_location, ["<Ctrl>L"])
        add("search", lambda: self.search_btn.set_active(not self.search_btn.get_active()), ["<Ctrl>F"])
        add("new-tab", lambda: self.new_tab(self.tab().file), ["<Ctrl>T"])
        add("close-tab", lambda: self.tabview.close_page(self.tabview.get_selected_page()), ["<Ctrl>W"])
        add("toggle-sidebar", lambda: self.sidebar_btn.set_active(not self.sidebar_btn.get_active()), ["F9"])
        add("toggle-view", lambda: self.set_view("list" if self.view_mode == "grid" else "grid"))
        add("open", self.open_selected, ["<Ctrl>O"])
        add("open-tab", self.open_in_tabs)
        add("open-with", self.open_with)
        add("cut", lambda: self.clip(True), ["<Ctrl>X"])
        add("copy", lambda: self.clip(False), ["<Ctrl>C"])
        add("paste", self.paste, ["<Ctrl>V"])
        add("rename", self.rename, ["F2"])
        add("trash", self.trash, ["Delete"])
        add("delete-permanently", self.delete_permanently, ["<Shift>Delete", "<Shift>KP_Delete"])
        add("new-folder", self.new_folder, ["<Ctrl><Shift>N"])
        add("select-all", lambda: self.tab().sel.select_all(), ["<Ctrl>A"])
        add("toggle-split", self.toggle_split, ["F3"])
        add("switch-pane", self.switch_pane, ["F4"])
        add("copy-other", lambda: self.send_to_other(False), ["F5"])
        add("move-other", lambda: self.send_to_other(True), ["F6"])
        add("undo", self.undo, ["<Ctrl>Z"])
        self.acts["undo"].set_enabled(False)
        add("favorite-add", lambda: self.add_favorites(self._selected_dirs()))
        add("favorite-remove", lambda: self.remove_favorites(self._selected_dirs()))
        add("favorite-toggle-here", self.toggle_favorite_here, ["<Ctrl>D"])
        add("side-fav-remove", self._side_fav_remove)
        add("side-open", self._side_open)
        add("side-open-tab", self._side_open_tab)
        add("side-rename", self._side_rename)
        add("side-reset", self._side_reset)
        add("side-unmount", self._side_unmount)
        add("zoom-in", lambda: self.zoom(1), ["<Ctrl>plus", "<Ctrl>equal", "<Ctrl>KP_Add"])
        add("zoom-out", lambda: self.zoom(-1), ["<Ctrl>minus", "<Ctrl>KP_Subtract"])
        add("zoom-reset", lambda: self.zoom(0), ["<Ctrl>0", "<Ctrl>KP_0"])
        add("new-file", self.new_file, ["<Ctrl><Alt>N"])
        add("copy-path", self.copy_path, ["<Ctrl><Shift>C"])
        add("new-window", self.new_window, ["<Ctrl>N"])
        add("tab-new-window", self.tab_new_window)
        add("tab-duplicate", self.tab_duplicate)
        add("tab-close-others", self.tab_close_others)
        add("tab-close", lambda: self.tabview.close_page(self._menu_target()))
        add("compress", self.compress)
        add("extract", self.extract)
        add("preview", self.preview)
        add("set-wallpaper", self.set_wallpaper)
        add("show-in-folder", self.show_in_folder)
        add("toggle-hidden", lambda: self.lookup_action("show-hidden").activate(None))
        add("terminal", self.open_terminal)
        add("properties", self.properties)
        add("empty-trash", self.empty_trash)
        add("restore", lambda: self.restore(self.tab().selected_infos()))
        add("restore-all", lambda: self.restore([self.tab().fmodel.get_item(i)
                                                  for i in range(self.tab().fmodel.get_n_items())]))
        add("about", self.about)

        v = Gio.SimpleAction.new("view", GLib.VariantType("s"))
        v.connect("activate", lambda a, p: self.set_view(p.get_string()))
        self.add_action(v)
        app.set_accels_for_action("win.view('grid')", ["<Ctrl>1"])
        app.set_accels_for_action("win.view('list')", ["<Ctrl>2"])

        hidden = Gio.SimpleAction.new_stateful("show-hidden", None, GLib.Variant("b", False))
        hidden.connect("activate", self._toggle_hidden)
        self.add_action(hidden)
        app.set_accels_for_action("win.show-hidden", ["<Ctrl>H"])

        look = Gio.SimpleAction.new_stateful("translucent", None, GLib.Variant("b", self.translucent))
        look.connect("activate", lambda a, p: self.set_translucent(not self.translucent))
        self.add_action(look)
        sort = Gio.SimpleAction.new_stateful("sort", GLib.VariantType("s"), GLib.Variant("s", "name"))
        sort.connect("activate", self._on_sort)
        self.add_action(sort)
        desc = Gio.SimpleAction.new_stateful("sort-desc", None, GLib.Variant("b", False))
        desc.connect("activate", self._on_sort_desc)
        self.add_action(desc)

    def _build_menus(self):
        def section(items):
            m = Gio.Menu()
            for label, action in items:
                m.append(label, action)
            return m

        def sort_menu():
            return section([("Name", "win.sort::name"), ("Modified", "win.sort::modified"),
                            ("Size", "win.sort::size"), ("Type", "win.sort::type"),
                            ("Reverse Order", "win.sort-desc")])

        def hidden_when_disabled(label, action):
            mi = Gio.MenuItem.new(label, action)
            mi.set_attribute_value("hidden-when", GLib.Variant("s", "action-disabled"))
            return mi

        item = Gio.Menu()
        opens = section([("Open", "win.open"), ("Open in New Tab", "win.open-tab"),
                         ("Open With…", "win.open-with")])
        preview = Gio.MenuItem.new("Preview", "win.preview")
        preview.set_attribute_value("accel", GLib.Variant("s", "space"))
        opens.append_item(preview)
        opens.append_item(hidden_when_disabled("Set as Background", "win.set-wallpaper"))
        opens.append_item(hidden_when_disabled("Show in Folder", "win.show-in-folder"))
        opens.append_item(hidden_when_disabled("Open in Terminal", "win.terminal"))
        item.append_section(None, opens)
        item.append_section(None, section([("Cut", "win.cut"), ("Copy", "win.copy"), ("Copy Path", "win.copy-path")]))
        archives = Gio.Menu()
        archives.append("Compress…", "win.compress")
        archives.append_item(hidden_when_disabled("Extract Here", "win.extract"))
        item.append_section(None, archives)
        item.append_section(None, section([("Rename…", "win.rename"), ("Move to Trash", "win.trash"),
                                                   ("Delete Permanently…", "win.delete-permanently")]))
        panes = Gio.Menu()
        panes.append_item(hidden_when_disabled("Copy to Other Pane", "win.copy-other"))
        panes.append_item(hidden_when_disabled("Move to Other Pane", "win.move-other"))
        item.append_section(None, panes)
        favs = Gio.Menu()
        favs.append_item(hidden_when_disabled("Add to Favorites", "win.favorite-add"))
        favs.append_item(hidden_when_disabled("Remove from Favorites", "win.favorite-remove"))
        item.append_section(None, favs)
        item.append_section(None, section([("Properties", "win.properties")]))

        def make_bg():
            # "Show/Hide Hidden Files" is a plain entry (not a tick box): a tick box makes GTK
            # reserve an indicator column on every row of the menu.
            bg = Gio.Menu()
            bg.append_section(None, section([("New Folder", "win.new-folder"), ("New File…", "win.new-file"),
                                             ("Paste", "win.paste")]))
            bg.append_section(None, section([
                ("Select All", "win.select-all"),
                ("Hide Hidden Files" if self.show_hidden else "Show Hidden Files", "win.toggle-hidden")]))
            bg.append_section(None, section([("Open in New Tab", "win.new-tab"), ("Open in Terminal", "win.terminal"),
                                             ("Copy Folder Path", "win.copy-path"), ("Split View", "win.toggle-split")]))
            here = self.tab().file if self.tab() else None
            fav_label = ("Remove from Favorites" if here is not None and self.is_favorite(here)
                         else "Add Folder to Favorites")
            bg.append_section(None, section([(fav_label, "win.favorite-toggle-here")]))
            tail = Gio.Menu()
            tail.append_submenu("Sort By", sort_menu())
            tail.append("Properties", "win.properties")
            bg.append_section(None, tail)
            return bg

        bg = make_bg()
        self._make_bg_menu = make_bg

        trash = Gio.Menu()
        trash.append_section(None, section([("Restore", "win.restore"), ("Open", "win.open")]))
        trash.append_section(None, section([("Delete Permanently…", "win.trash")]))
        trash_bg = section([("Restore All", "win.restore-all"), ("Empty Trash…", "win.empty-trash")])
        self.menus = {"item": item, "bg": bg, "trash": trash, "trash-bg": trash_bg}

        main = Gio.Menu()
        main.append_section("Sort By", sort_menu())
        main.append_section(None, section([("New Window", "win.new-window"), ("Undo", "win.undo")]))
        main.append_section(None, section([("Show Hidden Files", "win.show-hidden"),
                                           ("Translucent Blur", "win.translucent"),
                                           ("About Roost Xplorer", "win.about")]))
        self.menu_btn.set_menu_model(main)
        MenuStyle.get().attach(self.menu_btn.get_popover())

    # ---- sidebar
    # ---- favorites
    def _add_favorite_rows(self):
        if not self.favorites:
            row = Gtk.ListBoxRow(activatable=False, selectable=False,
                                 child=Gtk.Label(label="Right-click a folder and choose “Add to Favorites”", wrap=True,
                                                 xalign=0, margin_top=6, margin_bottom=6, css_classes=["dim-label", "caption"]))
            row.section, row.loc, row.volume, row.key, row.mount = 1, None, None, None, None
            row.default_label = row.shown_label = ""
            row.fav, row.header_text = False, "Favorites"
            self.side_list.append(row)
            return
        for n, uri in enumerate(self.favorites):
            f = Gio.File.new_for_uri(uri)
            self._side_row("folder-symbolic", display_name(f), 1, f, key="fav:" + uri, fav=True,
                           header="Favorites" if n == 0 else None)

    def is_favorite(self, file):
        return file.get_uri() in self.favorites

    def add_favorites(self, files):
        added = 0
        for f in files:
            if file_is_dir(f) and not self.is_favorite(f):
                self.favorites.append(f.get_uri())
                added += 1
        if added:
            save_config({"favorites": self.favorites})
            self.rebuild_sidebar()
            self.toast(f"Added {plural(added, 'folder')} to Favorites")
        self.update_actions()

    def remove_favorites(self, files):
        uris = {f.get_uri() for f in files}
        kept = [u for u in self.favorites if u not in uris]
        if len(kept) != len(self.favorites):
            removed = len(self.favorites) - len(kept)
            self.favorites = kept
            save_config({"favorites": self.favorites})
            self.rebuild_sidebar()
            self.toast(f"Removed {plural(removed, 'folder')} from Favorites")
        self.update_actions()

    def toggle_favorite_here(self):
        here = self.tab().file
        if here.get_uri_scheme() != "file":
            return
        (self.remove_favorites if self.is_favorite(here) else self.add_favorites)([here])

    def _selected_dirs(self):
        return [info_file(i) for i in self.tab().selected_infos() if is_dir(i)]

    def _side_header(self, row, before):
        separate = before is not None and before.section != row.section
        title = getattr(row, "header_text", None)
        if not (separate or title):
            row.set_header(None)
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if separate:
            box.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        if title:
            box.append(Gtk.Label(label=title.upper(), xalign=0, margin_start=12, margin_top=4, margin_bottom=2,
                                 css_classes=["caption-heading", "dim-label"]))
        row.set_header(box)

    def _side_row(self, icon, label, section, file=None, volume=None, key=None, mount=None, fav=False, header=None,
                  usage=False):
        shown = self.labels.get(key, label) if key else label
        box = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4)
        if isinstance(icon, str):
            box.append(Gtk.Image(icon_name=icon))
        else:
            box.append(Gtk.Image(gicon=icon))
        box.append(Gtk.Label(label=shown, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
        if mount is not None and mount_is_removable(mount):  # USB sticks, SD cards, network shares: one click to remove safely
            eject = Gtk.Button(icon_name="media-eject-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat", "circular", "eject-button"],
                               tooltip_text=("Disconnect" if mount.get_volume() is None else
                                             "Eject" if mount.can_eject() else "Unmount"))
            eject.connect("clicked", lambda *_: self.unmount_mount(mount, shown))
            box.append(eject)
        bar = None
        if usage and file is not None:  # a thin bar under disks showing how full they are
            bar = Gtk.ProgressBar(css_classes=["disk-usage"], margin_start=28, margin_end=6, margin_bottom=4, visible=False)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            outer.append(box)
            outer.append(bar)
            box.set_margin_bottom(1)
        row = Gtk.ListBoxRow(child=outer if bar is not None else box)
        row.usage_bar = bar
        row.section, row.loc, row.volume, row.key, row.mount = section, file, volume, key, mount
        row.default_label, row.shown_label = label, shown
        row.fav, row.header_text = fav, header
        if fav and file is not None and not file.query_exists(None):
            box.set_opacity(0.5)
        if key:  # disks: show the real name and location on hover, so renamed labels stay identifiable
            where = file.get_path() if file is not None and file.get_path() else ""
            row.base_tooltip = f"{label}\n{where}".strip() if where or shown != label else label
            row.set_tooltip_text(row.base_tooltip)
        click = Gtk.GestureClick(button=3)
        click.connect("pressed", self._on_side_menu, row)
        row.add_controller(click)
        if fav and file is not None:
            drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
            drag.connect("prepare", lambda src, x, y, uri=file.get_uri():
                         Gdk.ContentProvider.new_for_value(FAV_DRAG_PREFIX + uri))
            drag.connect("drag-begin", lambda src, d, r=row: r.add_css_class("dragging"))
            drag.connect("drag-end", lambda src, d, delete, r=row: r.remove_css_class("dragging"))
            row.add_controller(drag)
        self.side_list.append(row)

    def _on_side_menu(self, gesture, n, x, y, row):
        self._ctx_row = row
        menu = Gio.Menu()
        first = Gio.Menu()
        if row.volume is not None:
            first.append("Mount", "win.side-open")
        else:
            first.append("Open", "win.side-open")
            first.append("Open in New Tab", "win.side-open-tab")
        menu.append_section(None, first)
        if row.fav:
            favs = Gio.Menu()
            favs.append("Remove from Favorites", "win.side-fav-remove")
            menu.append_section(None, favs)
        if row.key:
            labels = Gio.Menu()
            labels.append("Rename Label…", "win.side-rename")
            if row.key in self.labels:
                labels.append("Reset Label", "win.side-reset")
            menu.append_section(None, labels)
        if row.mount is not None and (row.mount.can_unmount() or row.mount.can_eject()):
            eject = Gio.Menu()
            eject.append("Eject" if row.mount.can_eject() else "Unmount", "win.side-unmount")
            menu.append_section(None, eject)
        pop = Gtk.PopoverMenu.new_from_model(menu)
        pop.set_parent(row)
        pop.set_has_arrow(False)
        pop.set_halign(Gtk.Align.START)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)
        MenuStyle.get().attach(pop)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _side_drop_row(self, y):
        row = self.side_list.get_row_at_y(int(y))
        return row if row is not None and row.loc is not None else None

    def _over_favorites_heading(self, y):
        """The widget (heading, or the hint row when there are no favorites yet) that adds a favorite when dropped on."""
        for row in iter_children(self.side_list):
            if not isinstance(row, Gtk.ListBoxRow) or getattr(row, "header_text", None) != "Favorites":
                continue
            if not row.fav:  # the "right-click a folder…" hint shown while the list is empty
                ok, b = row.compute_bounds(self.side_list)
                if ok and b.get_y() <= y <= b.get_y() + b.get_height():
                    return row
            header = row.get_header()
            if header is not None:
                ok, b = header.compute_bounds(self.side_list)
                if ok and b.get_y() <= y <= b.get_y() + b.get_height():
                    return header
        return None

    def _side_drop_highlight(self, row, header=None):
        if row is not self._drop_row:
            if self._drop_row is not None:
                self._drop_row.remove_css_class("drop-hover")
            self._drop_row = row
            if row is not None:
                row.add_css_class("drop-hover")
        if header is not self._drop_header:
            if self._drop_header is not None:
                self._drop_header.remove_css_class("drop-hover")
            self._drop_header = header
            if header is not None:
                header.add_css_class("drop-hover")

    def _side_motion(self, target, x, y):
        value = target.get_value()
        if isinstance(value, str):
            self._side_drop_highlight(None)
            return self._fav_reorder_motion(target, x, y)
        self._fav_mark(None, False)
        return self._side_drop_motion(target, x, y)

    def _side_drop_any(self, target, value, x, y):
        if isinstance(value, str):
            return self._fav_reorder_drop(target, value, x, y)
        return self._side_drop(target, value, x, y)

    def _side_drop_motion(self, target, x, y):
        row = self._side_drop_row(y)
        if row is not None:
            self._side_drop_highlight(row)
            return DND_ACTIONS
        heading = self._over_favorites_heading(y)
        self._side_drop_highlight(None, heading)
        return DND_ACTIONS if heading is not None else 0  # accept both copy and move, or a plain drag is refused

    def _side_drop(self, target, value, x, y):
        row = self._side_drop_row(y)
        heading = self._over_favorites_heading(y) if row is None else None
        self._side_drop_highlight(None)
        if row is not None:
            return self.drop_files(value.get_files(), row.loc, copy=ctrl_held(target))
        if heading is not None:
            folders = [f for f in value.get_files() if file_is_dir(f)]
            if not folders:
                self.toast("Only folders can be added to Favorites")
                return False
            self.add_favorites(folders)
            return True
        return False

    # ---- reordering favorites by dragging
    def _fav_slot(self, y):
        """Where a dragged favorite would land: (index among favorites, row to draw the line at, line goes below it)."""
        rows = [r for r in iter_children(self.side_list) if isinstance(r, Gtk.ListBoxRow) and r.fav]
        if not rows:
            return None
        first, last = rows[0].compute_bounds(self.side_list)[1], rows[-1].compute_bounds(self.side_list)[1]
        if y < first.get_y() - 14 or y > last.get_y() + last.get_height() + 14:
            return None
        for i, r in enumerate(rows):
            b = r.compute_bounds(self.side_list)[1]
            if y < b.get_y() + b.get_height() / 2:
                return i, r, False
        return len(rows), rows[-1], True

    def _fav_mark(self, row, below):
        if self._fav_mark_row is not None:
            self._fav_mark_row.remove_css_class("drop-line-before")
            self._fav_mark_row.remove_css_class("drop-line-after")
        self._fav_mark_row = row
        if row is not None:
            row.add_css_class("drop-line-after" if below else "drop-line-before")

    @staticmethod
    def _dragged_favorite(value):
        return value[len(FAV_DRAG_PREFIX):] if isinstance(value, str) and value.startswith(FAV_DRAG_PREFIX) else None

    def _fav_reorder_motion(self, target, x, y):
        slot = self._fav_slot(y) if self._dragged_favorite(target.get_value()) else None
        self._fav_mark(slot[1] if slot else None, slot[2] if slot else False)
        return Gdk.DragAction.MOVE if slot else 0

    def _fav_reorder_drop(self, target, value, x, y):
        uri = self._dragged_favorite(value)
        slot = self._fav_slot(y)
        self._fav_mark(None, False)
        if uri is None or slot is None or uri not in self.favorites:
            return False
        index = slot[0]
        old = self.favorites.index(uri)
        self.favorites.remove(uri)
        if old < index:
            index -= 1  # everything after the old spot moved up by one
        self.favorites.insert(index, uri)
        save_config({"favorites": self.favorites})
        self.rebuild_sidebar()
        return True

    def _side_open(self):
        row = self._ctx_row
        if row is not None:
            self._on_side_activated(self.side_list, row)

    def _side_fav_remove(self):
        row = self._ctx_row
        if row is not None and row.fav and row.loc is not None:
            self.remove_favorites([row.loc])

    def _side_open_tab(self):
        row = self._ctx_row
        if row is not None and row.loc is not None:
            self.new_tab(row.loc)

    def _side_rename(self):
        row = self._ctx_row
        if row is None or not row.key:
            return

        def apply(name):
            self.labels[row.key] = name
            save_config({"labels": self.labels})
            self.rebuild_sidebar()

        what, itself = ("favorite", "folder") if row.fav else ("disk", "disk")
        self._prompt("Rename Label", "Rename", row.shown_label, apply,
                     body=f"Only changes how this {what} is named in the sidebar. The {itself} itself, its name and its path stay as “{row.default_label}”.")

    def _side_reset(self):
        row = self._ctx_row
        if row is not None and row.key in self.labels:
            del self.labels[row.key]
            save_config({"labels": self.labels})
            self.rebuild_sidebar()

    def _side_unmount(self):
        row = self._ctx_row
        if row is not None and row.mount is not None:
            self.unmount_mount(row.mount, row.shown_label)

    def unmount_mount(self, mount, label):
        """Unmount (and for USB sticks and the like, power off) a disk, letting the system ask for a password."""
        eject = mount.can_eject()
        removable = mount_is_removable(mount)

        def done(m, res):
            try:
                (m.eject_with_operation_finish if eject else m.unmount_with_operation_finish)(res)
                if mount.get_volume() is None:
                    self.toast(f"Disconnected “{label}”")
                else:
                    self.toast(f"“{label}” can now be safely removed" if removable else f"Unmounted “{label}”")
            except GLib.Error as e:
                if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.FAILED_HANDLED):
                    return  # the password prompt was cancelled; the system already told the user
                if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.BUSY):
                    self.toast(f"“{label}” is in use. Close anything that is using it and try again.")
                else:
                    self.toast(f"Can't {'eject' if eject else 'unmount'} “{label}”: {e.message}")

        operation = Gtk.MountOperation(parent=self)
        if eject:
            mount.eject_with_operation(Gio.MountUnmountFlags.NONE, operation, None, done)
        else:
            mount.unmount_with_operation(Gio.MountUnmountFlags.NONE, operation, None, done)

    def rebuild_sidebar(self):
        self.side_list.remove_all()
        home = GLib.get_home_dir()
        self._side_row("user-home-symbolic", "Home", 0, Gio.File.new_for_path(home))
        places = [
            (GLib.UserDirectory.DIRECTORY_DESKTOP, "user-desktop-symbolic", "Desktop"),
            (GLib.UserDirectory.DIRECTORY_DOCUMENTS, "folder-documents-symbolic", "Documents"),
            (GLib.UserDirectory.DIRECTORY_DOWNLOAD, "folder-download-symbolic", "Downloads"),
            (GLib.UserDirectory.DIRECTORY_MUSIC, "folder-music-symbolic", "Music"),
            (GLib.UserDirectory.DIRECTORY_PICTURES, "folder-pictures-symbolic", "Pictures"),
            (GLib.UserDirectory.DIRECTORY_VIDEOS, "folder-videos-symbolic", "Videos"),
        ]
        for d, icon, label in places:
            p = GLib.get_user_special_dir(d)
            if p and p != home and os.path.isdir(p):
                self._side_row(icon, label, 0, Gio.File.new_for_path(p))
        self._add_favorite_rows()
        self._side_row("user-trash-symbolic", "Trash", 2, Gio.File.new_for_uri("trash:///"))
        self._side_row("drive-harddisk-symbolic", "Computer", 3, Gio.File.new_for_path("/"), key="path:/", usage=True)
        for mount in self.vm.get_mounts():
            if not mount.is_shadowed():
                self._side_row(mount.get_symbolic_icon(), mount.get_name(), 3, mount.get_root(),
                               key=disk_key(mount, mount.get_root()), mount=mount, usage=True)
        for vol in self.vm.get_volumes():
            if vol.get_mount() is None and vol.can_mount():
                self._side_row(vol.get_symbolic_icon(), vol.get_name(), 3, None, vol, key=disk_key(vol))
        self.sync_sidebar()
        self.refresh_disk_usage()

    def refresh_disk_usage(self):
        """Ask each disk row how full its disk is (asynchronously: a slow network share must not freeze us)."""
        for row in iter_children(self.side_list):
            bar = getattr(row, "usage_bar", None)
            if bar is not None and row.loc is not None:
                row.loc.query_filesystem_info_async("filesystem::size,filesystem::free", GLib.PRIORITY_LOW, None,
                                                    self._on_disk_usage, row)

    def _on_disk_usage(self, file, res, row):
        bar = row.usage_bar
        try:
            info = file.query_filesystem_info_finish(res)
        except GLib.Error:
            bar.set_visible(False)
            return
        size = info.get_attribute_uint64("filesystem::size")
        free = info.get_attribute_uint64("filesystem::free")
        if not size:
            bar.set_visible(False)
            return
        fraction = max(0.0, min(1.0, (size - free) / size))
        if not bar.get_visible():
            bar.set_fraction(0)  # the first time: fill up from empty
        bar.set_visible(True)
        animate_fraction(bar, fraction, 450)
        if fraction >= 0.9:
            bar.add_css_class("full")
        else:
            bar.remove_css_class("full")
        row.set_tooltip_text(f"{row.base_tooltip}\n{GLib.format_size(free)} free of {GLib.format_size(size)} ({round(fraction * 100)}% used)")

    def _usage_tick(self):
        self.refresh_disk_usage()
        return True

    def sync_sidebar(self):
        tab = self.tab() if hasattr(self, "tabview") else None
        self.side_list.unselect_all()
        if tab is None or tab.file is None:
            return
        best = None
        for row in iter_children(self.side_list):
            if isinstance(row, Gtk.ListBoxRow) and row.loc is not None and row.loc.equal(tab.file):
                best = row
        if best is not None:
            self.side_list.select_row(best)

    def _on_side_activated(self, lb, row):
        if row.volume is not None:
            self.mount_volume(row.volume, row.shown_label)
        elif row.loc is not None:
            if row.fav and not row.loc.query_exists(None):
                self.toast(f"“{row.shown_label}” no longer exists. Right-click it to remove it from Favorites.")
                return
            self.go(row.loc)

    def mount_volume(self, vol, label):
        # A mount operation lets the system ask for a password. Without one the request is made "non-interactive"
        # and internal disks are simply refused with "Not authorized to perform operation".
        self.toast(f"Mounting {label}…")
        vol.mount(Gio.MountMountFlags.NONE, Gtk.MountOperation(parent=self), None,
                  lambda v, res: self._on_volume_mounted(v, res, label))

    def _on_volume_mounted(self, vol, res, label):
        try:
            vol.mount_finish(res)
        except GLib.Error as e:
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.FAILED_HANDLED):
                return  # the password prompt was cancelled; the system already told the user
            if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED):
                self.toast(f"Can't mount {label}: {e.message}")
                return
        mount = vol.get_mount()
        if mount is not None:
            self.go(mount.get_default_location() or mount.get_root())

    # ---- tabs & navigation
    def container(self):
        page = self.tabview.get_selected_page()
        return page.get_child() if page else None

    def tab(self):
        """The active folder pane of the current tab."""
        c = self.container()
        return c.active if c else None

    def tabs(self):
        """Every folder pane in every tab."""
        return [p for i in range(self.tabview.get_n_pages())
                for p in self.tabview.get_nth_page(i).get_child().panes]

    def new_tab(self, file):
        pane = FolderTab(self, file)
        pane.set_view(self.view_mode)
        cont = TabContainer(self, pane)
        cont.page = self.tabview.append(cont)
        cont.refresh_title()
        self.tabview.set_selected_page(cont.page)
        self.schedule_session_save()

    def _menu_target(self):
        return self._menu_page or self.tabview.get_selected_page()

    def _on_tab_menu(self, tabview, page):
        self._menu_page = page
        many = tabview.get_n_pages() > 1
        self.acts["tab-new-window"].set_enabled(many)
        self.acts["tab-close-others"].set_enabled(many)

    def _new_empty_window(self):
        win = Window(self.get_application(), Gio.File.new_for_path(GLib.get_home_dir()), empty=True)
        win.set_default_size(max(600, self.get_width()), max(400, self.get_height()))
        win.present()
        return win

    def _on_create_window(self, tabview):
        """The user dragged a tab out of the tab bar: give it a window of its own."""
        return self._new_empty_window().tabview

    def _on_page_attached(self, tabview, page, position):
        """A tab (and the panes in it) now belongs to this window. Point them here, wherever they came from."""
        cont = page.get_child()
        if isinstance(cont, TabContainer):
            cont.win, cont.page = self, page
            for pane in cont.panes:
                pane.win = self
            cont.refresh_title()
            self.schedule_session_save()
            if tabview.get_selected_page() is page:
                self._on_tab_changed()

    def new_window(self):
        """Ctrl+N: another window, in the folder you are looking at."""
        self.get_application().open_window(self.tab().file if self.tab() else None)

    def tab_new_window(self):
        page = self._menu_target()
        if page is not None and self.tabview.get_n_pages() > 1:
            self.tabview.transfer_page(page, self._new_empty_window().tabview, 0)

    def tab_duplicate(self):
        page = self._menu_target()
        if page is not None:
            self.new_tab(page.get_child().active.file)

    def tab_close_others(self):
        page = self._menu_target()
        if page is not None:
            self.tabview.close_other_pages(page)

    def _on_pages_changed(self, *a):
        if self.tabview.get_n_pages() == 0:
            self.close()
        else:
            self.schedule_session_save()

    def active_changed(self, cont):
        self.schedule_session_save()
        if cont is self.container():
            self._on_tab_changed()

    def toggle_split(self):
        self.container().toggle_split()

    def switch_pane(self):
        c = self.container()
        if c.other() is not None:
            c.set_active(c.other())
            c.active.focus_view()

    def send_to_other(self, move):
        c = self.container()
        other, files = c.other(), self.tab().selected_files()
        if other is not None and files:
            self.transfer(files, other.file, move)

    def go(self, file):
        self.tab().navigate(file)

    def _on_tab_changed(self):
        tab = self.tab()
        if tab is None:
            return
        self.search_entry.set_text(tab.query_text)
        self.update_search_spinner()
        self.tab_location_changed(tab)
        self.update_actions()

    def tab_location_changed(self, tab):
        self.schedule_session_save()
        if tab is not self.tab():
            return
        self.set_title(f"{display_name(tab.file)} — Roost Xplorer")  # the taskbar shows this
        if not tab.query_text and self.search_entry.get_text():
            self.search_entry.set_text("")  # navigating away from a search clears the search box
        self._build_crumbs(tab.file)
        self.acts["back"].set_enabled(tab.can_back())
        self.acts["forward"].set_enabled(tab.can_forward())
        self.acts["up"].set_enabled(tab.file.get_parent() is not None)
        self.sync_sidebar()
        self.update_view_button()
        in_trash = tab.file.get_uri_scheme() == "trash"
        self.trash_btn.set_visible(in_trash)
        self.restore_btn.set_visible(in_trash)

    def _build_crumbs(self, file):
        while (c := self.crumbs.get_first_child()) is not None:
            self.crumbs.remove(c)
        parts = []
        if file.get_uri_scheme() == "file":
            path, home = file.get_path(), GLib.get_home_dir()
            if path == home or path.startswith(home + "/"):
                parts.append(("Home", home))
                rest, cur = [p for p in path[len(home):].split("/") if p], home
            else:
                parts.append(("/", "/"))
                rest, cur = [p for p in path.split("/") if p], "/"
            for r in rest:
                cur = os.path.join(cur, r)
                parts.append((r, cur))
            parts = [(l, Gio.File.new_for_path(p)) for l, p in parts]
        else:
            parts = [(display_name(file), file)]
        for i, (label, f) in enumerate(parts):
            last = i == len(parts) - 1
            if i:
                self.crumbs.append(Gtk.Image(icon_name="go-next-symbolic", css_classes=["crumb-sep"]))
            b = Gtk.Button(label=label, css_classes=["flat", "crumb"] + (["crumb-current"] if last else []))
            b.connect("clicked", lambda _b, f=f: self.go(f))
            self.crumbs.append(b)
        adj = self.crumb_scroll.get_hadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper()) and False)

    def focus_location(self):
        tab = self.tab()
        self.loc_entry.set_text(tab.file.get_path() or tab.file.get_uri())
        self.loc_stack.set_visible_child_name("entry")
        self.loc_entry.grab_focus()

    def _loc_key(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.loc_stack.set_visible_child_name("crumbs")
            self.tab().focus_view()
            return True
        return False

    def open_location(self, text):
        text = text.strip()
        self.loc_stack.set_visible_child_name("crumbs")
        if not text:
            return
        f = Gio.File.parse_name(text)
        try:
            t = f.query_info("standard::type", 0, None).get_file_type()
        except GLib.Error as e:
            self.toast(e.message)
            return
        if t == Gio.FileType.DIRECTORY:
            self.go(f)
        else:
            self.launch(f)
        self.tab().focus_view()

    def _update_search_placeholder(self):
        self.search_entry.set_placeholder_text(
            "Search this folder and its subfolders" if self.deep_search else "Filter this folder")

    def _on_deep_toggled(self, button):
        self.deep_search = button.get_active()
        self.save_prefs()
        self._update_search_placeholder()
        tab = self.tab()
        if tab is not None and tab.query_text:
            text = tab.query_text
            tab.query_text = None  # force set_query to re-evaluate in the new mode
            tab.set_query(text)

    def update_search_spinner(self):
        tab = self.tab()
        busy = tab is not None and tab.searching and not tab.search_done
        self.search_spinner.set_visible(busy)
        self.search_spinner.set_spinning(busy)

    def set_wallpaper(self):
        infos = self.tab().selected_infos()
        path = info_file(infos[0]).get_path() if len(infos) == 1 else None
        if not path:
            return
        try:
            subprocess.Popen(["plasma-apply-wallpaperimage", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.toast("Background changed")
        except OSError:
            self.toast("Setting the background needs KDE Plasma")

    def preview(self):
        if self.get_visible_dialog() is not None:
            return
        tab = self.tab()
        bs = tab.sel.get_selection()
        if bs.get_size() == 0:
            return
        PreviewDialog(self, tab, bs.get_nth(0)).present(self)

    def _on_window_key(self, ctrl, keyval, keycode, state):
        """Space previews the selected file; the Menu key (or Shift+F10) opens the right-click menu.
        Neither applies while you are typing somewhere or a dialog is open."""
        menu_keys = (Gdk.KEY_Menu, getattr(Gdk, "KEY_MenuKB", Gdk.KEY_Menu))
        shift_f10 = keyval == Gdk.KEY_F10 and state & Gdk.ModifierType.SHIFT_MASK and not state & (
            Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK)
        if keyval in menu_keys or shift_f10:
            if self.get_visible_dialog() is not None or isinstance(self.get_focus(), Gtk.Editable):
                return False
            return self.keyboard_menu()
        if keyval != Gdk.KEY_space or state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK
                                                | Gdk.ModifierType.SHIFT_MASK):
            return False
        if self.get_visible_dialog() is not None or isinstance(self.get_focus(), Gtk.Editable):
            return False
        if not self.acts["preview"].get_enabled():
            return False
        self.preview()
        return True

    def keyboard_menu(self):
        focus = self.get_focus()
        if is_inside(focus, self.side_list):  # in the sidebar: the menu of the focused entry
            row = focus
            while row is not None and not isinstance(row, Gtk.ListBoxRow):
                row = row.get_parent()
            if row is not None and (row.loc is not None or row.volume is not None):
                self._on_side_menu(None, 1, row.get_width() / 2, row.get_height() / 2, row)
                return True
            return False
        tab = self.tab()
        if tab is None:
            return False
        tab.keyboard_menu(focus)
        return True

    def compress(self):
        tab = self.tab()
        files = tab.selected_files()
        if not files or not tab.file.get_path():
            return
        if len(files) == 1:
            first = files[0]
            stem = first.get_basename() if file_is_dir(first) else (os.path.splitext(first.get_basename())[0] or first.get_basename())
        else:
            stem = "Archive"
        formats = list(ARCHIVE_FORMATS)
        folder = tab.file

        def with_extension(name, fmt):
            for ext in ARCHIVE_FORMATS.values():
                if name.lower().endswith(ext):
                    name = name[: -len(ext)]
            return name + ARCHIVE_FORMATS[fmt]

        d = Adw.AlertDialog(heading=f"Compress {plural(len(files))}")
        entry = Gtk.Entry(text=with_extension(stem, self.compress_format), hexpand=True, activates_default=True)
        choice = Gtk.DropDown.new_from_strings(formats)
        choice.set_selected(formats.index(self.compress_format))
        choice.connect("notify::selected", lambda *a: entry.set_text(with_extension(entry.get_text(), formats[choice.get_selected()])))
        row = Gtk.Box(spacing=8)
        row.append(entry)
        row.append(choice)
        d.set_extra_child(row)
        d.add_response("cancel", "Cancel")
        d.add_response("ok", "Compress")
        d.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("ok")
        d.set_close_response("cancel")

        def on_response(dlg, response):
            name = entry.get_text().strip()
            if response != "ok" or not name or "/" in name:
                if response == "ok" and "/" in name:
                    self.toast("Names can't contain “/”")
                return
            fmt = formats[choice.get_selected()]
            self.compress_format = fmt
            self.save_prefs()
            dest = unique_dest(folder, with_extension(name, fmt), False).get_path()
            self.run_job(Job(f"Compressing {plural(len(files))}"), lambda job: compress_job(job, files, dest, fmt))

        d.connect("response", on_response)
        d.present(self)
        entry.grab_focus()
        entry.select_region(0, len(entry.get_text()) - len(ARCHIVE_FORMATS[self.compress_format]))

    def extract(self):
        archives = [f for f, i in zip(self.tab().selected_files(), self.tab().selected_infos())
                    if archive_kind(i.get_display_name())]
        if archives:
            self.run_job(Job(f"Extracting {plural(len(archives), 'archive')}"), lambda job: extract_job(job, archives))

    def new_file(self):
        tab = self.tab()
        folder = tab.file

        def apply(name):
            if "/" in name:
                self.toast("Names can't contain “/”")
                return
            target = folder.get_child(name)
            try:
                target.create(Gio.FileCreateFlags.NONE, None).close(None)
            except GLib.Error as e:
                self.toast(f"“{name}” already exists" if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.EXISTS) else e.message)
                return
            self.push_undo({"kind": "mkdir", "file": target})
            self.toast(f"Created “{name}”", undo=True)
            tab.select_when_ready(name)

        self._prompt("New File", "Create", "Untitled.txt", apply, select_stem=True)

    def copy_path(self):
        tab = self.tab()
        files = tab.selected_files() or [tab.file]
        self.cut_files = []  # the clipboard now holds text, not files
        text = "\n".join(f.get_path() or f.get_uri() for f in files)
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))
        self.toast("Path copied" if len(files) == 1 else f"{len(files)} paths copied")

    def show_in_folder(self):
        tab = self.tab()
        infos = tab.selected_infos()
        if len(infos) == 1:
            f = info_file(infos[0])
            tab.select_when_ready(f.get_basename())
            tab.navigate(f.get_parent())

    def _on_search_mode(self, *a):
        if not self.searchbar.get_search_mode():
            self.search_entry.set_text("")
            if self.tab():
                self.tab().focus_view()

    # ---- view / sort / hidden
    def set_view(self, mode):
        self.view_mode = mode
        self.save_prefs()
        for t in self.tabs():
            t.set_view(mode)
        self.update_view_button()

    def zoom(self, direction):
        """Make grid icons bigger (+1), smaller (-1) or back to normal (0)."""
        i = ZOOM_STEPS.index(self.icon_size)
        new = ZOOM_STEPS.index(72) if direction == 0 else max(0, min(len(ZOOM_STEPS) - 1, i + direction))
        if ZOOM_STEPS[new] == self.icon_size:
            return
        self.icon_size = ZOOM_STEPS[new]
        self.save_prefs()
        for t in self.tabs():
            t.apply_zoom()
        if self.view_mode != "grid":
            self.toast(f"Icon size {self.icon_size}px (shown in the grid view)")

    def resync_folders(self):
        """Double-check the folders on screen against the disk (catches changes a watcher can miss)."""
        cont = self.container()
        if cont is not None:
            for pane in cont.panes:
                pane.dirlist.resync()

    def apply_look(self):
        if self.translucent:
            self.add_css_class("translucent")
        else:
            self.remove_css_class("translucent")
        action = self.lookup_action("translucent")
        if action is not None:
            action.set_state(GLib.Variant("b", self.translucent))
        if self.get_mapped():
            WaylandBlur.get().set(self, self.translucent)

    def set_translucent(self, on):
        self.translucent = on
        self.save_prefs()
        for win in self.get_application().get_windows():  # every open window changes together
            if isinstance(win, Window):
                win.translucent = on
                win.apply_look()

    def update_view_button(self):
        grid = self.view_mode == "grid"
        self.view_btn.set_icon_name("view-list-symbolic" if grid else "view-grid-symbolic")
        self.view_btn.set_tooltip_text("Show as List (Ctrl+2)" if grid else "Show as Grid (Ctrl+1)")

    def _toggle_hidden(self, action, _p):
        self.show_hidden = not self.show_hidden
        self.save_prefs()
        action.set_state(GLib.Variant("b", self.show_hidden))
        for t in self.tabs():
            t.filter.changed(Gtk.FilterChange.DIFFERENT)
            if t.searching:
                text = t.query_text
                t.query_text = None
                t.set_query(text)

    def _on_sort(self, action, p):
        action.set_state(p)
        self.sort_key = p.get_string()
        self.save_prefs()
        self._apply_sort()

    def _on_sort_desc(self, action, _p):
        self.sort_desc = not self.sort_desc
        self.save_prefs()
        action.set_state(GLib.Variant("b", self.sort_desc))
        self._apply_sort()

    def _apply_sort(self):
        for t in self.tabs():
            t.sort_by(self.sort_key, self.sort_desc)

    # ---- actions
    def update_actions(self):
        tab = self.tab()
        if tab is None or not self.acts:
            return
        infos = tab.selected_infos()
        n = len(infos)
        trash = tab.file.get_uri_scheme() == "trash"
        self.acts["open"].set_enabled(n > 0)
        self.acts["preview"].set_enabled(n > 0 and info_file(infos[0]).get_path() is not None)
        writable_here = tab.file.get_path() is not None and not trash
        self.acts["compress"].set_enabled(n > 0 and writable_here and not tab.searching)
        self.acts["extract"].set_enabled(n > 0 and writable_here and all(
            not is_dir(i) and archive_kind(i.get_display_name()) for i in infos))
        self.acts["show-in-folder"].set_enabled(tab.searching and n == 1)
        self.acts["open-tab"].set_enabled(any(is_dir(i) for i in infos))
        self.acts["open-with"].set_enabled(n == 1 and not is_dir(infos[0]))
        self.acts["set-wallpaper"].set_enabled(
            n == 1 and not is_dir(infos[0]) and content_type(infos[0]).startswith("image/")
            and info_file(infos[0]).get_path() is not None and shutil.which("plasma-apply-wallpaperimage") is not None)
        self.acts["cut"].set_enabled(n > 0 and not trash)
        self.acts["copy"].set_enabled(n > 0 and not trash)
        self.acts["rename"].set_enabled(n == 1 and not trash)
        self.acts["trash"].set_enabled(n > 0)
        self.acts["delete-permanently"].set_enabled(n > 0)
        self.acts["paste"].set_enabled(not trash)
        local = tab.file.get_path() is not None
        self.acts["terminal"].set_enabled(local and not trash and (n == 0 or (n == 1 and is_dir(infos[0]))))
        self.acts["empty-trash"].set_enabled(trash and tab.fmodel.get_n_items() > 0)
        self.acts["restore"].set_enabled(trash and n > 0)
        self.acts["restore-all"].set_enabled(trash and tab.fmodel.get_n_items() > 0)
        other = self.container().other()
        self.acts["switch-pane"].set_enabled(other is not None)
        self.acts["copy-other"].set_enabled(other is not None and n > 0 and not trash)
        self.acts["move-other"].set_enabled(other is not None and n > 0 and not trash)
        self.acts["new-folder"].set_enabled(not trash)
        self.acts["new-file"].set_enabled(not trash and local)
        dirs = [info_file(i) for i in infos if is_dir(i)]
        self.acts["favorite-add"].set_enabled(not trash and any(not self.is_favorite(d) for d in dirs))
        self.acts["favorite-remove"].set_enabled(not trash and bool(dirs) and all(self.is_favorite(d) for d in dirs))
        self.acts["favorite-toggle-here"].set_enabled(tab.file.get_uri_scheme() == "file")

    def toast(self, msg, undo=False):
        if self._last_toast is not None:
            self._last_toast.dismiss()
        t = Adw.Toast.new(msg)
        if undo:
            t.set_button_label("Undo")
            t.set_action_name("win.undo")
            t.set_timeout(8)
        self._last_toast = t
        self.toasts.add_toast(t)

    # ---- background jobs (progress, cancel, undo)
    def run_job(self, job, work):
        self.jobs.append(job)
        self._add_job_row(job)
        self.ops_label.set_text("0%")
        self.ops_bar.set_fraction(0)
        self.ops_btn.set_visible(True)

        def thread():
            try:
                work(job)
            except Cancelled:
                job.cancelled = True
            except OSError as e:
                job.error = f"{e.strerror}: {os.path.basename(e.filename)}" if e.strerror and e.filename else str(e)
            except Exception as e:  # noqa: BLE001
                job.error = getattr(e, "message", None) or str(e)
            GLib.idle_add(self._job_finished, job)

        threading.Thread(target=thread, daemon=True).start()
        if len(self.jobs) == 1:
            GLib.timeout_add(120, self._jobs_tick)

    def _add_job_row(self, job):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        top = Gtk.Box(spacing=8)
        title = Gtk.Label(label=job.title, xalign=0, hexpand=True, css_classes=["heading"])
        cancel = Gtk.Button(icon_name="process-stop-symbolic", css_classes=["flat", "circular"], tooltip_text="Cancel")
        cancel.connect("clicked", lambda *_: job.cancellable.cancel())
        top.append(title)
        top.append(cancel)
        bar = Gtk.ProgressBar()
        status = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, css_classes=["dim-label", "caption"])
        detail = Gtk.Label(xalign=0, css_classes=["caption"])
        for w in (top, bar, status, detail):
            box.append(w)
        self.ops_list.append(box)
        self.job_rows[job] = (box, bar, status, detail)

    def _jobs_tick(self):
        if not self.jobs:
            return False
        now = GLib.get_monotonic_time()
        for job in self.jobs:
            box, bar, status, detail = self.job_rows[job]
            if job.total:
                animate_fraction(bar, job.fraction)
                detail.set_text(job.detail())
            else:
                bar.pulse()
            status.set_text(("Cancelling…" if job.cancellable.is_cancelled() else job.status))
        self.ops_btn.set_visible(True)
        avg = sum(j.fraction for j in self.jobs) / len(self.jobs)
        if any(j.total for j in self.jobs):
            animate_fraction(self.ops_bar, avg)
            self.ops_label.set_text(f"{round(avg * 100)}%")
            first = self.jobs[0]
            self.ops_btn.set_tooltip_text(f"{first.title}\n{first.detail()}")
        else:
            self.ops_bar.pulse()
            self.ops_label.set_text("…")
        return True

    def _hide_ops(self):
        if not self.jobs:  # a newer job keeps the indicator alive
            self.ops_btn.set_visible(False)
            self.ops_btn.popdown()
        return False

    def _job_finished(self, job):
        self.jobs.remove(job)
        self.ops_list.remove(self.job_rows.pop(job)[0])
        if not self.jobs:
            self.ops_label.set_text("Done" if not (job.error or job.cancelled) else ("Failed" if job.error else "Stopped"))
            if not (job.error or job.cancelled):
                self.ops_bar.set_fraction(1)
            GLib.timeout_add(1800, self._hide_ops)
        GLib.timeout_add(1500, lambda: (self.refresh_disk_usage(), False)[1])  # free space just changed
        GLib.timeout_add(500, lambda: (self.resync_folders(), False)[1])  # make sure the listing shows the result
        if job.undo:
            self.undo_stack.append(job.undo)
            del self.undo_stack[:-30]
            self.acts["undo"].set_enabled(True)
        if job.error:
            self.toast(f"Error: {job.error}")
        elif job.cancelled:
            self.toast("Cancelled" + (" (finished items stay)" if job.undo else ""), undo=bool(job.undo))
        else:
            self.toast(job.message or "Done", undo=bool(job.undo))
        return False

    def push_undo(self, entry):
        self.undo_stack.append(entry)
        del self.undo_stack[:-30]
        self.acts["undo"].set_enabled(True)

    def undo(self):
        if not self.undo_stack:
            self.toast("Nothing to undo")
            return
        entry = self.undo_stack.pop()
        self.acts["undo"].set_enabled(bool(self.undo_stack))
        self.run_job(Job("Undoing"), lambda job: undo_job(job, entry))

    @staticmethod
    def _count_entries(menu):
        n = 0
        for i in range(menu.get_n_items()):
            link = menu.get_item_link(i, "section") or menu.get_item_link(i, "submenu")
            n += 1 if (link is None or menu.get_item_link(i, "submenu")) else Window._count_entries(link)
        return n

    def popup(self, widget, x, y, kind):
        """Pop a context menu, opening on whichever side of the click has room.

        GTK squeezes (and scrolls) a popover that doesn't fit on its side of the click,
        so pick the side from the menu's height instead.
        """
        model = self._make_bg_menu() if kind == "bg" else self.menus[kind]
        need = self._menu_height.get(kind) or 36 * self._count_entries(model) + 24
        pos = widget.translate_coordinates(self, x, y)
        wy = pos[1] if pos else self.get_height() / 2
        below, above = self.get_height() - wy, wy
        if need <= below:
            side = Gtk.PositionType.BOTTOM
        elif need <= above:
            side = Gtk.PositionType.TOP
        else:
            side = Gtk.PositionType.BOTTOM if below >= above else Gtk.PositionType.TOP

        pop = Gtk.PopoverMenu.new_from_model(model)
        if kind in ("bg", "trash-bg"):
            # GTK height-caps (and scrolls) a menu hung from a large widget, so hang it from a small
            # one instead and point at the click through coordinates relative to that widget.
            anchor = self.tab().menu_anchor
            moved = widget.translate_coordinates(anchor, x, y)
            if moved:
                widget, x, y = anchor, moved[0], moved[1]
        pop.set_parent(widget)
        pop.set_has_arrow(False)
        pop.set_position(side)
        pop.set_halign(Gtk.Align.START)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)

        def remember(p):  # learn the real height so the next menu is placed exactly
            GLib.idle_add(lambda: self._menu_height.__setitem__(kind, p.get_height()) and False)

        pop.connect("map", remember)
        MenuStyle.get().attach(pop)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def launch(self, file, ask=False):
        launcher = Gtk.FileLauncher.new(file)
        launcher.set_always_ask(ask)

        def done(l, res):
            try:
                l.launch_finish(res)
            except GLib.Error as e:
                if not e.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                    self.toast(e.message)

        launcher.launch(self, None, done)

    def open_selected(self):
        infos = self.tab().selected_infos()
        for i in infos:
            if is_dir(i):
                if len(infos) == 1:
                    self.go(info_file(i))
                else:
                    self.new_tab(info_file(i))
            else:
                self.launch(info_file(i))

    def open_in_tabs(self):
        for i in self.tab().selected_infos():
            if is_dir(i):
                self.new_tab(info_file(i))

    def open_with(self):
        files = self.tab().selected_files()
        if files:
            self.launch(files[0], ask=True)

    def clip(self, cut):
        files = self.tab().selected_files()
        if not files:
            return
        self.cut_files = files if cut else []
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(files_value(files)))
        self.toast(f"{'Cut' if cut else 'Copied'} {len(files)} item{'s' if len(files) != 1 else ''}")

    def paste(self):
        self.get_clipboard().read_value_async(Gdk.FileList.__gtype__, GLib.PRIORITY_DEFAULT, None, self._on_paste)

    def _on_paste(self, cb, res):
        try:
            files = cb.read_value_finish(res).get_files()
        except GLib.Error:
            self.toast("Nothing to paste")
            return
        move = bool(self.cut_files) and len(files) == len(self.cut_files) and all(
            a.equal(b) for a, b in zip(files, self.cut_files))
        if move:
            self.cut_files = []
        self.transfer(files, self.tab().file, move)

    def drop_files(self, files, dest, copy=False):
        if dest.get_uri_scheme() == "trash":
            self.trash_files(files)
            return True
        if any(dest.equal(f) or dest.has_prefix(f) for f in files):
            return False
        self.transfer(files, dest, move=not copy)
        return True

    def _ask_conflict(self, job, src, target, both_dirs):
        """Called from a worker thread: show the dialog and wait for the answer. Returns (choice, apply_to_all)."""
        answer, done, holder = {}, threading.Event(), {}

        def describe(f):
            try:
                i = f.query_info("standard::size,standard::type,time::modified", NOFOLLOW, None)
            except GLib.Error:
                return "—"
            when = i.get_modification_date_time()
            bits = [] if i.get_file_type() == Gio.FileType.DIRECTORY else [GLib.format_size(i.get_size())]
            if when:
                bits.append("modified " + when.to_local().format("%-d %b %Y, %H:%M"))
            return " · ".join(bits) or "—"

        def show():
            name = src.get_basename()
            d = Adw.AlertDialog(heading=f"“{name}” already exists",
                                body=f"The folder “{display_name(target.get_parent())}” already has an item with this name.\n\n"
                                     f"Existing:  {describe(target)}\nNew:  {describe(src)}")
            d.set_body_use_markup(False)
            # the dialog lists responses bottom-up: Cancel last, the safe/default choice on top, Replace near the bottom
            d.add_response("cancel", "Cancel")
            d.add_response("replace", "Replace")
            d.add_response("skip", "Skip")
            d.add_response("keep", "Keep Both")
            if both_dirs:
                d.add_response("merge", "Merge")
                d.set_default_response("merge")
                d.set_response_appearance("merge", Adw.ResponseAppearance.SUGGESTED)
            else:
                d.set_default_response("keep")
                d.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
            d.set_response_appearance("replace", Adw.ResponseAppearance.DESTRUCTIVE)
            d.set_close_response("cancel")
            check = None
            if job.multi or both_dirs:
                check = Gtk.CheckButton(label="Apply to all remaining conflicts", halign=Gtk.Align.CENTER)
                d.set_extra_child(check)

            def on_response(dlg, response):
                answer["choice"] = response
                answer["all"] = bool(check and check.get_active())
                done.set()

            d.connect("response", on_response)
            holder["dialog"] = d
            d.present(self)
            return False

        GLib.idle_add(show)
        while not done.wait(0.2):
            if job.cancellable.is_cancelled():  # cancelled from the progress popover meanwhile
                GLib.idle_add(lambda: holder["dialog"].force_close() if "dialog" in holder else None)
                raise Cancelled()
        if answer["choice"] == "cancel":
            raise Cancelled()
        return answer["choice"], answer["all"]

    def transfer(self, files, dest, move):
        files = list(files)
        job = Job(f"{'Moving' if move else 'Copying'} {plural(len(files))}")
        job.resolver = self._ask_conflict
        self.run_job(job, lambda job: transfer_job(job, files, dest, move))

    def trash(self):
        files = self.tab().selected_files()
        if not files:
            return
        if self.tab().file.get_uri_scheme() == "trash":
            self.confirm_permanent_delete(files)  # things in the Trash can only be deleted for good
        else:
            self.trash_files(files)

    def delete_permanently(self):
        """Shift+Delete: delete for good, skipping the Trash, after asking."""
        files = self.tab().selected_files()
        if files:
            self.confirm_permanent_delete(files)

    def confirm_permanent_delete(self, files):
        files = list(files)
        if len(files) == 1:
            name = files[0].get_basename()
            what = f"“{name}” and everything inside it" if file_is_dir(files[0]) else f"“{name}”"
        else:
            what = f"{len(files)} items (and everything inside any folders)" if any(file_is_dir(f) for f in files) else f"{len(files)} items"
        d = Adw.AlertDialog(heading="Delete Permanently?",
                            body=f"{what} will be deleted forever, without going to the Trash. This can't be undone.")
        d.add_response("cancel", "Cancel")
        d.add_response("delete", "Delete Permanently")
        d.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_default_response("cancel")  # a stray Enter must not delete anything
        d.set_close_response("cancel")
        d.connect("response", lambda dlg, r: r == "delete" and self.trash_files(files, permanent=True))
        d.present(self)

    TERMINALS = ["konsole", "ptyxis", "gnome-terminal", "kgx", "xfce4-terminal", "alacritty",
                 "kitty", "foot", "wezterm", "xterm"]

    def open_terminal(self):
        tab = self.tab()
        infos = tab.selected_infos()
        target = info_file(infos[0]) if len(infos) == 1 and is_dir(infos[0]) else tab.file
        path = target.get_path()
        term = next((t for t in self.TERMINALS if GLib.find_program_in_path(t)), None)
        if not path or term is None:
            self.toast("No terminal emulator found" if path else "Can't open a terminal here")
            return
        try:
            launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.NONE)
            launcher.set_cwd(path)
            launcher.spawnv([term] if term != "konsole" else [term, "--workdir", path])
        except GLib.Error as e:
            self.toast(e.message)

    def properties(self):
        tab = self.tab()
        files = tab.selected_files() or [tab.file]
        dlg = Adw.Dialog(title="Properties", content_width=440)
        dlg.closed = False
        dlg.connect("closed", lambda d: setattr(d, "closed", True))

        def row(group, title, value, selectable=True):
            r = Adw.ActionRow(title=title, subtitle=GLib.markup_escape_text(value or "—"), subtitle_selectable=selectable)
            r.add_css_class("property")
            group.add(r)
            return r

        attrs = ",".join(["standard::display-name", "standard::icon", "standard::type", "standard::size",
                          "standard::fast-content-type", "standard::symlink-target", "time::modified",
                          "time::access", "time::created", "owner::user", "owner::group", "unix::mode"])
        infos = []
        for f in files:
            try:
                infos.append(f.query_info(attrs, NOFOLLOW, None))
            except GLib.Error as e:
                self.toast(e.message)
                return

        page = Adw.PreferencesPage()
        head = Adw.PreferencesGroup()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8)
        icon = Gtk.Image(pixel_size=64, gicon=infos[0].get_icon() if len(infos) == 1 else None,
                         icon_name="folder-symbolic" if len(infos) > 1 else None)
        title = display_name(files[0]) if len(files) == 1 else f"{len(files)} items"
        box.append(icon)
        box.append(Gtk.Label(label=title, css_classes=["title-2"], wrap=True, justify=Gtk.Justification.CENTER,
                             selectable=True))
        head.add(box)
        page.add(head)

        group = Adw.PreferencesGroup()
        page.add(group)

        def when(ts):
            return ts.to_local().format("%A, %-d %B %Y, %H:%M") if ts else ""

        if len(files) == 1:
            info, f = infos[0], files[0]
            row(group, "Type", type_description(info))
            parent = f.get_parent()
            row(group, "Location", (parent.get_path() or parent.get_uri()) if parent else "/")
            if info.has_attribute("standard::symlink-target"):
                row(group, "Link target", info.get_symlink_target())
            size_row = row(group, "Size", "Calculating…" if is_dir(info) else
                           f"{GLib.format_size(info.get_size())} ({info.get_size():,} bytes)")
            row(group, "Modified", when(info.get_modification_date_time()))
            row(group, "Accessed", when(info.get_access_date_time()))
            row(group, "Created", when(info.get_creation_date_time()))
            if info.has_attribute("unix::mode"):
                mode = info.get_attribute_uint32("unix::mode") & 0o7777
                bits = "".join(("r" if mode & (4 << sh) else "-") + ("w" if mode & (2 << sh) else "-") +
                               ("x" if mode & (1 << sh) else "-") for sh in (6, 3, 0))
                row(group, "Permissions", f"{bits}  ({mode:04o})")
            row(group, "Owner", f"{info.get_attribute_string('owner::user') or '?'} : "
                                f"{info.get_attribute_string('owner::group') or '?'}")
        else:
            parents = {(x.get_parent().get_path() if x.get_parent() else "") for x in files}
            row(group, "Location", parents.pop() if len(parents) == 1 else "Multiple locations")
            dirs = sum(is_dir(i) for i in infos)
            row(group, "Contents", f"{len(files) - dirs} files, {dirs} folders")
            size_row = row(group, "Total size", "Calculating…")

        if len(files) > 1 or is_dir(infos[0]):
            def measure():
                total = count = 0
                stack = list(files)
                while stack and not dlg.closed:
                    f = stack.pop()
                    try:
                        i = f.query_info("standard::type,standard::size", NOFOLLOW, None)
                        if i.get_file_type() == Gio.FileType.DIRECTORY:
                            en = f.enumerate_children("standard::name", NOFOLLOW, None)
                            while (ci := en.next_file(None)) is not None:
                                stack.append(f.get_child(ci.get_name()))
                        else:
                            total += i.get_size()
                        count += 1
                    except GLib.Error:
                        pass
                    if count % 400 == 0:
                        GLib.idle_add(show, total, count, False)
                GLib.idle_add(show, total, count, True)

            def show(total, count, done):
                if not dlg.closed:
                    size_row.set_subtitle(f"{GLib.format_size(total)} · {count:,} items" + ("" if done else " …"))

            threading.Thread(target=measure, daemon=True).start()

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(page)
        dlg.set_child(view)
        dlg.present(self)

    def restore(self, infos):
        wanted = {i.get_attribute_byte_string("trash::orig-path") for i in infos}
        wanted.discard(None)
        if not wanted:
            self.toast("Nothing to restore")
            return
        self.run_job(Job(f"Restoring {plural(len(wanted))}"), lambda job: restore_from_trash(job, wanted))

    def empty_trash(self):
        if self.tab().file.get_uri_scheme() != "trash":
            return
        d = Adw.AlertDialog(heading="Empty Trash?", body="All items in the Trash will be deleted permanently.")
        d.add_response("cancel", "Cancel")
        d.add_response("empty", "Empty Trash")
        d.set_response_appearance("empty", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_close_response("cancel")
        d.connect("response", lambda d, r: r == "empty" and self._do_empty_trash())
        d.present(self)

    def _do_empty_trash(self):
        def work(job):
            root = Gio.File.new_for_uri("trash:///")
            names = []
            en = root.enumerate_children("standard::name", NOFOLLOW, None)
            while (ci := en.next_file(None)) is not None:
                names.append(ci.get_name())
            job.total = len(names)
            for name in names:
                job.check()
                job.status = f"Deleting {name}"
                f = root.get_child(name)
                try:
                    f.delete(job.cancellable)
                except GLib.Error as e:
                    if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                        raise Cancelled() from e
                    delete_tree(f, job)
                job.done += 1
            job.message = "Trash emptied"

        self.run_job(Job("Emptying Trash"), work)

    def trash_files(self, files, permanent=False):
        files = list(files)
        job = Job(f"{'Deleting' if permanent else 'Moving to Trash:'} {plural(len(files))}")
        self.run_job(job, lambda job: trash_job(job, files, permanent))

    def _prompt(self, heading, label, initial, cb, select_stem=False, body=None):
        d = Adw.AlertDialog(heading=heading)
        if body:
            d.set_body(body)
        entry = Gtk.Entry(text=initial, activates_default=True)
        d.set_extra_child(entry)
        d.add_response("cancel", "Cancel")
        d.add_response("ok", label)
        d.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("ok")
        d.set_close_response("cancel")
        d.connect("response", lambda d, r: r == "ok" and entry.get_text().strip() and cb(entry.get_text().strip()))
        d.present(self)
        entry.grab_focus()
        if select_stem:
            entry.select_region(0, len(os.path.splitext(initial)[0]))

    def rename(self):
        files = self.tab().selected_files()
        if len(files) != 1:
            return
        f = files[0]

        def apply(name):
            if "/" in name:
                self.toast("Names can't contain “/”")
                return
            try:
                new = f.set_display_name(name, None)
            except GLib.Error as e:
                self.toast(e.message)
                return
            self.push_undo({"kind": "rename", "file": new, "old": f.get_basename()})
            self.toast(f"Renamed to “{name}”", undo=True)

        self._prompt("Rename", "Rename", f.get_basename(), apply, select_stem=True)

    def new_folder(self):
        dest = self.tab().file

        def apply(name):
            try:
                folder = dest.get_child(name)
                folder.make_directory(None)
            except GLib.Error as e:
                self.toast(e.message)
                return
            self.push_undo({"kind": "mkdir", "file": folder})
            self.toast(f"Created “{name}”", undo=True)

        self._prompt("New Folder", "Create", "Untitled Folder", apply, select_stem=False)

    def about(self):
        dlg = Adw.AboutDialog(application_name="Roost Xplorer", application_icon=APP_ID, version=VERSION,
                              developer_name="Aditya Kumar K", website=REPO_URL, issue_url=REPO_URL + "/issues",
                              license_type=Gtk.License.MIT_X11, copyright="© 2026 Aditya Kumar K",
                              comments="A sleek, dark file manager for Linux with tabs, split view and "
                                       "search inside subfolders.")
        dlg.present(self)


CONFIG = os.path.join(GLib.get_user_config_dir(), "roost-xplorer.json")
_OLD_CONFIG = os.path.join(GLib.get_user_config_dir(), "sleekfiles.json")  # earlier name of this app


def _migrate_config():
    """Keep favorites, labels and tabs from the earlier name of the app."""
    if not os.path.exists(CONFIG) and os.path.exists(_OLD_CONFIG):
        try:
            shutil.copyfile(_OLD_CONFIG, CONFIG)
        except OSError:
            pass


_migrate_config()


def load_config():
    try:
        with open(CONFIG) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data):
    merged = {**load_config(), **data}  # read first: opening the file for writing truncates it
    try:
        tmp = CONFIG + ".tmp"
        with open(tmp, "w") as f:
            json.dump(merged, f, indent=1)
        os.replace(tmp, CONFIG)  # atomic, so a crash can't leave a half-written settings file
    except OSError:
        pass


def as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def iter_children(widget):
    c = widget.get_first_child()
    while c is not None:
        yield c
        c = c.get_next_sibling()


# --------------------------------------------------------------------- app
class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.connect("activate", self.on_activate)
        self.connect("open", self.on_open)

    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(os.path.join(ASSETS, "icons"))
        Gtk.Window.set_default_icon_name(APP_ID)
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def explorer_windows(self):
        return [w for w in self.get_windows() if isinstance(w, Window)]

    def open_window(self, folder=None):
        """A new window. The first one restores your saved tabs; later ones start fresh and never save the session."""
        first = not self.explorer_windows()
        start = folder or Gio.File.new_for_path(GLib.get_home_dir())
        win = Window(self, start, restore=first and folder is None, primary=first)
        win.present()
        return win

    def on_activate(self, app):
        # launching the app again (app menu, Meta+E, ...) opens another window instead of just raising the old one
        self.open_window()

    def on_open(self, app, files, n, hint):
        # a folder opened from another app or the terminal gets a window of its own (several folders: one tab each)
        win = None
        for f in files:
            if win is None:
                win = self.open_window(f)
            else:
                win.new_tab(f)


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
