import os
import json
import time
import traceback
from datetime import datetime

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import platform

# ---------- CONFIG ----------
HISTORY_FILE = "print_history.json"

# ---------- HISTORY UTIL ----------
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(h):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Warning: cannot save history:", e)

def add_history_entry(order_id, customer, box_qty):
    h = load_history()
    h.append({
        "order_id": str(order_id),
        "customer": str(customer),
        "box_qty": int(box_qty),
        "timestamp": datetime.now().isoformat()
    })
    save_history(h)

def has_been_printed(order_id):
    h = load_history()
    return any(item.get("order_id") == str(order_id) for item in h)

# ---------- PLATFORM CHECK ----------
def is_android():
    return platform == "android"

# ---------- IMPORT MODULES BASED ON PLATFORM ----------
if not is_android():
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    PAGE_W_MM = 70
    PAGE_H_MM = 50
    MARGIN_MM = 5
    FONT_NAME = "Helvetica"
    FONT_NAME1 = "Helvetica-Bold"
    FONT_TTF = "arial.ttf"
    if os.path.exists(FONT_TTF):
        try:
            pdfmetrics.registerFont(TTFont("AppFont", FONT_TTF))
            FONT_NAME = "AppFont"
        except:
            FONT_NAME = "Helvetica"

    def create_pdf_80x50_left(order_id, customer, box_qty):
        pagesize = (PAGE_W_MM*mm, PAGE_H_MM*mm)
        filename = f"ORDER_{order_id}.pdf"
        try:
            c = canvas.Canvas(filename, pagesize=pagesize)
            margin = MARGIN_MM*mm
            width, height = pagesize
            usable_h = height - 2*margin
            part_h = usable_h / 3.0
            left_x = margin
            for i in range(int(box_qty)):
                order_font = max(10, min(int(part_h*0.8), 48))
                other_font = max(8, min(int(part_h*0.45), 30))
                y1 = height - margin - (part_h*0.3)
                c.setFont(FONT_NAME1, order_font)
                text1 = str(order_id)[:40]
                c.drawString(left_x, y1, text1)
                y2 = height - margin - part_h - (part_h*0.3)
                c.setFont(FONT_NAME, other_font)
                text2 = str(customer)[:40]
                c.drawString(left_x, y2, text2)
                y3 = height - margin - part_h*2.5 - (part_h*0.3)
                c.setFont(FONT_NAME, other_font)
                c.drawString(left_x, y3, f"BOX: # {i+1} / {box_qty}")
                c.showPage()
            c.save()
            return filename
        except Exception:
            if os.path.exists(filename):
                os.remove(filename)
            raise

    def open_pdf_by_platform(path):
        import subprocess
        abs_path = os.path.abspath(path)
        try:
            if platform == "win":
                os.startfile(abs_path)
            elif platform == "macosx":
                subprocess.call(["open", abs_path])
            else:
                subprocess.call(["xdg-open", abs_path])
        except Exception as e:
            print("open_pdf error:", e)

else:
    from jnius import autoclass
    import socket

    def escpos_bytes_for_label(order_id, customer, box_index, box_total, encoding='utf-8'):
        b = bytearray()
        b += b'\x1b\x40'
        b += b'\x1d\x21\x11' + order_id.encode(encoding, errors='replace') + b'\n'
        b += b'\x1d\x21\x00' + customer.encode(encoding, errors='replace') + b'\n'
        b += f"BOX: #{box_index}/{box_total}\n".encode(encoding)
        b += b'\n\n' + b'\x1d\x56\x00'
        return bytes(b)

    def find_paired_printers_pyjnius():
        try:
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            adapter = BluetoothAdapter.getDefaultAdapter()
            if adapter is None: return []
            paired = adapter.getBondedDevices()
            devices = []
            try:
                arr = paired.toArray()
                for dev in arr:
                    devices.append((dev.getName(), dev.getAddress()))
            except:
                it = paired.iterator()
                while it.hasNext():
                    dev = it.next()
                    devices.append((dev.getName(), dev.getAddress()))
            return devices
        except Exception as e:
            print("find_paired_printers_pyjnius error:", e)
            return []

    def print_via_bluetooth_pyjnius(mac_addr, payload_bytes):
        try:
            UUID = autoclass('java.util.UUID')
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            adapter = BluetoothAdapter.getDefaultAdapter()
            device = adapter.getRemoteDevice(mac_addr)
            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            socket = device.createRfcommSocketToServiceRecord(spp_uuid)
            if adapter.isDiscovering():
                adapter.cancelDiscovery()
            socket.connect()
            out = socket.getOutputStream()
            out.write(payload_bytes)
            out.flush()
            out.close()
            socket.close()
            return True, None
        except Exception as e:
            return False, str(e)

    def print_via_wifi_escpos(ip, port, payload_bytes, timeout=5):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            s.sendall(payload_bytes)
            s.close()
            return True, None
        except Exception as e:
            return False, str(e)

# ---------- UI SCREENS ----------
class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.clearcolor = (1,1,1,1)  # light background
        layout = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(12))
        inner = BoxLayout(orientation='vertical', size_hint=(.8, None), height=dp(420), spacing=dp(12),
                          pos_hint={'center_x': 0.5, 'center_y': 0.5})
        self.entry_order = TextInput(hint_text="Mã đơn hàng", font_size=dp(20), size_hint_y=None, height=dp(50),
                                     background_color=(1,1,1,1), foreground_color=(0,0,0,1))
        self.entry_customer = TextInput(hint_text="Tên khách", font_size=dp(20), size_hint_y=None, height=dp(50),
                                        background_color=(1,1,1,1), foreground_color=(0,0,0,1))
        self.entry_box = TextInput(hint_text="Số BOX", font_size=dp(20), size_hint_y=None, height=dp(50), input_filter='int',
                                   background_color=(1,1,1,1), foreground_color=(0,0,0,1))
        btn_print = Button(text="Xem & In", size_hint_y=None, height=dp(60), font_size=dp(20),
                           background_color=[0.7,0.85,1,1], color=(0,0,0,1))
        btn_print.bind(on_release=self.on_print)
        btn_history = Button(text="Lịch sử đơn đã in", size_hint_y=None, height=dp(60), font_size=dp(20),
                             background_color=[0.7,1,0.7,1], color=(0,0,0,1))
        btn_history.bind(on_release=lambda *_: setattr(self.manager, "current", "history"))
        btn_dupes = Button(text="Đơn bị in trùng", size_hint_y=None, height=dp(60), font_size=dp(20),
                           background_color=[1,0.8,0.6,1], color=(0,0,0,1))
        btn_dupes.bind(on_release=lambda *_: setattr(self.manager, "current", "dupes"))
        inner.add_widget(self.entry_order)
        inner.add_widget(self.entry_customer)
        inner.add_widget(self.entry_box)
        inner.add_widget(btn_print)
        inner.add_widget(btn_history)
        inner.add_widget(btn_dupes)
        layout.add_widget(inner)
        self.add_widget(layout)

    # ... phần còn lại giữ nguyên như code trước, chỉ cần thêm màu light theme cho popup, labels, buttons ...



    def on_print(self, *_):
        oid = self.entry_order.text.strip()
        cust = self.entry_customer.text.strip()
        box = self.entry_box.text.strip()
        from kivy.uix.popup import Popup
        if not oid or not cust or not box:
            Popup(title="Thiếu thông tin", content=Label(text="Vui lòng nhập đầy đủ thông tin!"), size_hint=(.8,.4)).open()
            return
        try:
            box_n = int(box)
            if box_n <=0: raise ValueError
        except:
            Popup(title="Sai định dạng", content=Label(text="Số BOX phải là số nguyên dương"), size_hint=(.8,.4)).open()
            return
        if has_been_printed(oid):
            boxl = BoxLayout(orientation='vertical', spacing=dp(12))
            boxl.add_widget(Label(text=f"Đơn {oid} đã được in trước đó. Có chắc muốn in lại?"))
            btnl = BoxLayout(spacing=dp(12))
            popup = Popup(title="Đơn trùng", content=boxl, size_hint=(.8,.4))
            def yes(*_):
                popup.dismiss()
                self.do_print(oid, cust, box_n)
            def no(*_):
                popup.dismiss()
            btn_yes = Button(text="Có", on_release=yes)
            btn_no = Button(text="Không", on_release=no)
            btnl.add_widget(btn_yes)
            btnl.add_widget(btn_no)
            boxl.add_widget(btnl)
            popup.open()
            return
        self.do_print(oid, cust, box_n)

    def do_print(self, oid, cust, box_n):
        from kivy.uix.popup import Popup
        try:
            if not is_android():
                # Desktop
                pdf_path = create_pdf_80x50_left(oid, cust, box_n)
                add_history_entry(oid, cust, box_n)
                import subprocess
                open_pdf_by_platform(pdf_path)
                Popup(title="Hoàn tất", content=Label(text=f"Đã tạo {pdf_path} và mở để in/kiểm tra."), size_hint=(.8,.4)).open()
            else:
                # Android
                request_android_permissions()
                android_show_print_review_and_print(self, oid, cust, box_n)
            self.entry_order.text = self.entry_customer.text = self.entry_box.text = ""
        except Exception as e:
            traceback.print_exc()
            Popup(title="Lỗi", content=Label(text=str(e)), size_hint=(.8,.4)).open()

# ---------- HISTORY / DUPES SCREENS ----------
class HistoryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation='vertical', padding=dp(12))
        scroll = ScrollView()
        self.container = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.container.bind(minimum_height=self.container.setter('height'))
        scroll.add_widget(self.container)
        btn_back = Button(text="Về trang chủ", size_hint_y=None, height=dp(50), font_size=dp(18), background_color=[0.6,0.6,0.6,1])
        btn_back.bind(on_release=lambda *_: setattr(self.manager, "current","home"))
        root.add_widget(scroll)
        root.add_widget(btn_back)
        self.add_widget(root)

    def on_enter(self, *args):
        self.refresh_history()

    def refresh_history(self):
        self.container.clear_widgets()
        data = load_history()
        counts = {}
        for it in data: counts[it.get("order_id")] = counts.get(it.get("order_id"),0)+1
        for it in reversed(data):
            oid = it.get("order_id")
            color = [1,0,0,1] if counts.get(oid,0)>1 else [0,0,0.5,1]
            lbl = Label(text=f"{oid} | {it.get('customer')} | BOX {it.get('box_qty')} | {it.get('timestamp')}", size_hint_y=None, height=dp(40), color=color, font_size=dp(18))
            self.container.add_widget(lbl)

class DupesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation='vertical', padding=dp(12))
        scroll = ScrollView()
        self.container = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.container.bind(minimum_height=self.container.setter('height'))
        scroll.add_widget(self.container)
        btn_back = Button(text="Về trang chủ", size_hint_y=None, height=dp(50), font_size=dp(18), background_color=[0.6,0.6,0.6,1])
        btn_back.bind(on_release=lambda *_: setattr(self.manager, "current","home"))
        root.add_widget(scroll)
        root.add_widget(btn_back)
        self.add_widget(root)

    def on_enter(self, *args):
        self.refresh_dupes()

    def refresh_dupes(self):
        self.container.clear_widgets()
        data = load_history()
        counts = {}
        for it in data: counts[it.get("order_id")] = counts.get(it.get("order_id"),0)+1
        for oid,cnt in counts.items():
            if cnt>1:
                lbl = Label(text=f"{oid} | số lần in: {cnt}", size_hint_y=None, height=dp(40), color=[1,0,0,1], font_size=dp(18))
                self.container.add_widget(lbl)

# ---------- ANDROID PREVIEW & PRINT ----------
if is_android():
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.uix.scrollview import ScrollView
    from kivy.core.window import Window

    def request_android_permissions():
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            Build = autoclass('android.os.Build')
            sdk = int(Build.VERSION.SDK)
            if sdk >= 23:
                Manifest = autoclass('android.Manifest$permission')
                perms = []
                try: perms.append(Manifest.BLUETOOTH); perms.append(Manifest.BLUETOOTH_ADMIN)
                except: pass
                try: perms.append(Manifest.BLUETOOTH_CONNECT); perms.append(Manifest.BLUETOOTH_SCAN)
                except: pass
                try: perms.append(Manifest.ACCESS_FINE_LOCATION)
                except: pass
                String = autoclass('java.lang.String'); StringArray = autoclass('[Ljava.lang.String;')
                jarr = StringArray(len(perms))
                for i,p in enumerate(perms): jarr[i]=p
                activity.requestPermissions(jarr,0)
        except Exception as e:
            print("request_android_permissions error:", e)

    def android_show_print_review_and_print(self, oid, cust, box_n):
        root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        scroll = ScrollView(size_hint=(1,None), size=(Window.width*0.9, Window.height*0.5))
        container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6), padding=dp(6))
        container.bind(minimum_height=container.setter('height'))
        for i in range(box_n):
            preview = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(120), padding=dp(8), spacing=dp(4))
            lbl_order = Label(text=oid, font_size=28, size_hint_y=None, height=dp(40), halign='left', valign='middle')
            lbl_order.bind(size=lbl_order.setter('text_size'))
            lbl_cust = Label(text=cust, font_size=18, size_hint_y=None, height=dp(36), halign='left', valign='middle')
            lbl_cust.bind(size=lbl_cust.setter('text_size'))
            lbl_box = Label(text=f"BOX: #{i+1} / {box_n}", font_size=18, size_hint_y=None, height=dp(36), halign='left', valign='middle')
            lbl_box.bind(size=lbl_box.setter('text_size'))
            preview.add_widget(lbl_order)
            preview.add_widget(lbl_cust)
            preview.add_widget(lbl_box)
            container.add_widget(preview)
        scroll.add_widget(container)
        root.add_widget(scroll)

        # --- WIFI INPUT ---
        wifi_box = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        ip_input = TextInput(hint_text="Printer IP", font_size=16)
        port_input = TextInput(hint_text="Port", font_size=16, input_filter='int')
        wifi_box.add_widget(ip_input)
        wifi_box.add_widget(port_input)
        root.add_widget(wifi_box)

        status = Label(text="", size_hint_y=None, height=dp(30))
        root.add_widget(status)
        btn_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        btn_print_bt = Button(text="In Bluetooth", font_size=18)
        btn_print_wifi = Button(text="In Wi-Fi", font_size=18)
        btn_cancel = Button(text="Hủy", font_size=18)
        btn_row.add_widget(btn_print_bt)
        btn_row.add_widget(btn_print_wifi)
        btn_row.add_widget(btn_cancel)
        root.add_widget(btn_row)

        popup = Popup(title="Xem & In nhãn", content=root, size_hint=(.95,.95))
        def do_bt_print(*_):
            devices = find_paired_printers_pyjnius()
            if not devices:
                status.text = "Không tìm thấy thiết bị BT"
                return
            for i in range(box_n):
                payload = escpos_bytes_for_label(oid, cust, i+1, box_n)
                ok, err = print_via_bluetooth_pyjnius(devices[0][1], payload)
                if not ok:
                    status.text = f"Lỗi BT: {err}"
                    return
            add_history_entry(oid, cust, box_n)
            status.text = f"Đã in {box_n} nhãn qua BT"

        def do_wifi_print(*_):
            ip = ip_input.text.strip()
            port = port_input.text.strip()
            if not ip or not port: 
                status.text = "Nhập IP & Port!"
                return
            try: port_n = int(port)
            except: 
                status.text = "Port không hợp lệ"
                return
            for i in range(box_n):
                payload = escpos_bytes_for_label(oid, cust, i+1, box_n)
                ok, err = print_via_wifi_escpos(ip, port_n, payload)
                if not ok:
                    status.text = f"Lỗi Wi-Fi: {err}"
                    return
            add_history_entry(oid, cust, box_n)
            status.text = f"Đã in {box_n} nhãn qua Wi-Fi"

        btn_print_bt.bind(on_release=do_bt_print)
        btn_print_wifi.bind(on_release=do_wifi_print)
        btn_cancel.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

# ---------- MAIN APP ----------
class OrderPrinterApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(HistoryScreen(name="history"))
        sm.add_widget(DupesScreen(name="dupes"))
        return sm

if __name__ == "__main__":
    OrderPrinterApp().run()
