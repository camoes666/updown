import asyncio
import json
import time
import pandas as pd
import numpy as np
import websockets
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from datetime import datetime
import tkinter as tk
from tkinter import ttk, font as tkFont
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import threading

# --- 스타일 및 색상 팔레트 (이전 버전을 기준으로 박스 색상 개선) ---
# 기본 배경 및 프레임 (이전 버전의 밝은 테마 유지)
COLOR_PRIMARY_BG = "#f0f0f0" # 밝은 회색 배경 (원래 #2c3e50에서 변경)
COLOR_CONTENT_BG = "#ffffff" # 컨텐츠/카드 배경 (원래 #ecf0f1에서 변경)
COLOR_TEXT_DARK = "#2c3e50"  # 어두운 텍스트
COLOR_TEXT_LIGHT = "#ffffff" # 밝은 텍스트 (주로 어두운 박스 위)
COLOR_TEXT_SECONDARY = "#7f8c8d" # 보조 회색 텍스트

# 박스 및 신호 색상 (세련된 톤으로 조정 시도)
BOX_UP_COLOR = "#27ae60"      # 차분한 녹색 (기존 #2ecc71 보다 약간 어둡게)
BOX_DOWN_COLOR = "#c0392b"    # 차분한 빨강 (기존 #e74c3c 보다 약간 어둡게)
BOX_FLAT_COLOR = "#7f8c8d"    # 중간 회색 (기존 #95a5a6 보다 약간 어둡게)
BOX_COUNT_BG_COLOR = "#3498db" # 결정 카운트 박스 배경 (파란색 계열)
BOX_COUNT_TEXT_COLOR = "#ffffff"

# 폰트 (이전 버전 스타일 유지 또는 약간 조정)
FONT_FAMILY_MAIN = "Arial" # 이전과 동일하게 Arial 사용
FONT_TITLE = (FONT_FAMILY_MAIN, 20, "bold")
FONT_SUBTITLE = (FONT_FAMILY_MAIN, 16, "bold") # 섹션 타이틀용
FONT_SIGNAL = (FONT_FAMILY_MAIN, 48, "bold")
FONT_INFO_HEADER = (FONT_FAMILY_MAIN, 12, "bold")
FONT_INFO_TEXT = (FONT_FAMILY_MAIN, 11)
FONT_STATUS = (FONT_FAMILY_MAIN, 10, "italic")

FONT_DECISION_TIME_TEXT = (FONT_FAMILY_MAIN, 30, "bold") # 크기 약간 조정
FONT_DECISION_COUNT_TEXT = (FONT_FAMILY_MAIN, 30, "bold")# 크기 약간 조정

FONT_SIZE_XSMALL = 9 # 또는 8, 적절한 작은 크기로 정의 (추가된 부분)

FONT_DECISION_COUNT_TEXT = (FONT_FAMILY_MAIN, 30, "bold")# 크기 약간 조정


# 전역 변수 (dtype 명시 포함)
SYMBOL = "btcusdt"
CANDLE_INTERVAL = 5
DECISION_INTERVAL = 60
WINDOW_SIZE = 60
MA5_PERIOD = 5
MA10_PERIOD = 10
SLOPE_PERIOD = 4
SIGNAL_LOG_FILE = "signal_log.txt"

BINANCE_WS_URL = f"wss://stream.binance.com:9443/ws/{SYMBOL}@ticker"

ticker_df_dtypes = {'event_time': 'int64', 'price': 'float64'}
ticker_df = pd.DataFrame(columns=list(ticker_df_dtypes.keys())).astype(ticker_df_dtypes)
candle_df_dtypes = {
    'candle_start_time': 'int64', 'open': 'float64', 'high': 'float64',
    'low': 'float64', 'close': 'float64'
}
candle_df = pd.DataFrame(columns=list(candle_df_dtypes.keys())).astype(candle_df_dtypes)

current_signal = "FLAT"
slope5, slope10 = 0.0, 0.0
last_decision_server_time_seconds = 0
countdown_seconds = DECISION_INTERVAL
last_processed_event_time = 0
decision_count = 0


class TradingSignalApp:
    def __init__(self, root):
        self.root = root
        self.selected_bet = tk.IntVar(value=5)
        self.selected_delay = tk.IntVar(value=0)
        self.pending_signal_data = None
        self.active_delay_timer = None
        self.root.title("Trading Signal Dashboard v2 (Improved Boxes)")
        self.root.geometry("1000x850") # 이전 크기 유지 또는 약간 조절
        self.root.configure(bg=COLOR_PRIMARY_BG)

        # ttk 스타일 설정
        style = ttk.Style()
        style.theme_use('clam') # 이전과 동일하게 clam 테마 사용

        style.configure('TFrame', background=COLOR_PRIMARY_BG)
        style.configure('Content.TFrame', background=COLOR_CONTENT_BG)
        style.configure('Card.TFrame', background=COLOR_CONTENT_BG, relief='raised', borderwidth=1) # 카드 테두리 얇게

        style.configure('TLabel', background=COLOR_PRIMARY_BG, foreground=COLOR_TEXT_DARK, font=FONT_INFO_TEXT)
        style.configure('Header.TLabel', font=FONT_TITLE, foreground=COLOR_TEXT_DARK, background=COLOR_PRIMARY_BG) # 헤더 강조
        style.configure('SubHeader.TLabel', font=FONT_SUBTITLE, foreground=COLOR_TEXT_DARK, background=COLOR_CONTENT_BG)

        style.configure('Symbol.TLabel', background=COLOR_PRIMARY_BG, foreground=COLOR_TEXT_DARK, font=FONT_INFO_HEADER)
        style.configure('Symbol.TEntry', fieldbackground=COLOR_CONTENT_BG, foreground=COLOR_TEXT_DARK, font=FONT_INFO_TEXT)
        style.configure('TButton', font=FONT_INFO_HEADER, background="#e0e0e0", foreground=COLOR_TEXT_DARK) # 버튼 색상 변경
        style.map('TButton', background=[('active', "#c0c0c0")])

        style.configure('Info.TLabelframe', background=COLOR_CONTENT_BG, relief='groove', borderwidth=1)
        style.configure('Info.TLabelframe.Label', font=FONT_INFO_HEADER, background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_DARK)
        style.configure('InfoData.TFrame', background=COLOR_CONTENT_BG)
        style.configure('InfoData.TLabel', background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_DARK, font=FONT_INFO_TEXT)
        style.configure('InfoValue.TLabel', background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_DARK, font=(FONT_INFO_TEXT[0], FONT_INFO_TEXT[1], "bold"))
        style.configure('TRadiobutton', background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_DARK, font=FONT_INFO_TEXT, anchor=tk.W) # Added for Radiobutton styling
        style.map('TRadiobutton',
            background=[('active', COLOR_CONTENT_BG)],
            indicatorcolor=[('selected', BOX_UP_COLOR), ('!selected', COLOR_TEXT_DARK)],
            foreground=[('active', COLOR_TEXT_DARK)]
        )


        # --- UI 구성 (이전 레이아웃 기반) ---
        self.main_frame = ttk.Frame(root, padding=20)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.header_frame = ttk.Frame(self.main_frame, padding=(0, 0, 0, 20))
        self.header_frame.pack(fill=tk.X)
        ttk.Label(self.header_frame, text="Up Down Trading Signal", style='Header.TLabel').pack(side=tk.LEFT)

        self.symbol_frame = ttk.Frame(self.header_frame)
        self.symbol_frame.pack(side=tk.RIGHT)
        ttk.Label(self.symbol_frame, text="Symbol:", style='Symbol.TLabel').pack(side=tk.LEFT, padx=5)
        self.symbol_entry = ttk.Entry(self.symbol_frame, width=12, style='Symbol.TEntry')
        self.symbol_entry.insert(0, SYMBOL.upper())
        self.symbol_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(self.symbol_frame, text="Change", command=self.change_symbol, style='TButton').pack(side=tk.LEFT, padx=5)

        content_frame = ttk.Frame(self.main_frame, style='Content.TFrame', padding=10)
        content_frame.pack(fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(content_frame, style='Content.TFrame', padding=10)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0) # Adjusted padding

        right_panel = ttk.Frame(content_frame, style='Content.TFrame', padding=10)
        # right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10,0)) # Commented out to remove right panel


        # --- 왼쪽 패널 구성 ---
        price_info_card = ttk.Frame(left_panel, style='Card.TFrame', padding=15)
        price_info_card.pack(fill=tk.X, pady=(0,15))
        self.price_label = ttk.Label(price_info_card, text="Current Price: $-.--", font=(FONT_FAMILY_MAIN, 22, "bold"), background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_DARK)
        self.price_label.pack(pady=(0, 5))
        self.time_label = ttk.Label(price_info_card, text="Last Update: -", font=FONT_INFO_TEXT, background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_SECONDARY)
        self.time_label.pack(pady=(0, 10))
        self.countdown_label = ttk.Label(price_info_card, text=f"Next Signal In: {DECISION_INTERVAL}s", font=(FONT_FAMILY_MAIN, 16), background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_DARK)
        self.countdown_label.pack(pady=(0, 5))

        # Decision Time 박스 - 스타일 개선
        ttk.Label(left_panel, text="Decision Time", style='SubHeader.TLabel', anchor='center').pack(fill=tk.X, pady=(15,3))
        self.decision_time_frame = tk.Frame(left_panel, bg=BOX_FLAT_COLOR, relief=tk.GROOVE, borderwidth=4) # 테두리, 기본 배경 변경
        self.decision_time_frame.pack(fill=tk.X, pady=(0,20), ipady=30) # 높이 증가
        self.decision_time_frame.pack_propagate(False)
        self.decision_time_label_var = tk.StringVar(value="--:--:--")
        self.decision_time_label = tk.Label(self.decision_time_frame, textvariable=self.decision_time_label_var,
                                            font=FONT_DECISION_TIME_TEXT, fg=COLOR_TEXT_LIGHT, bg=BOX_FLAT_COLOR, anchor='center')
        self.decision_time_label.pack(expand=True, fill=tk.BOTH)

        # Decision (신호) 박스 - 스타일 개선
        ttk.Label(left_panel, text="Decision", style='SubHeader.TLabel', anchor='center').pack(fill=tk.X, pady=(15,3))
        self.signal_card = tk.Label(left_panel, text="WAITING...", font=FONT_SIGNAL, width=8, height=1,
                                   bg=BOX_FLAT_COLOR, fg=COLOR_TEXT_LIGHT, relief=tk.RAISED, borderwidth=5) # 테두리, 기본 배경 변경
        self.signal_card.pack(fill=tk.X, pady=(0,20), ipady=10) # ipady로 높이 조절

        # Decision Count 박스 - 스타일 개선
        ttk.Label(left_panel, text="Decision Count", style='SubHeader.TLabel', anchor='center').pack(fill=tk.X, pady=(15,3))
        self.decision_count_frame = tk.Frame(left_panel, bg=BOX_COUNT_BG_COLOR, relief=tk.GROOVE, borderwidth=4) # 배경색, 테두리 변경
        self.decision_count_frame.pack(fill=tk.X, pady=(0,20), ipady=30) # 높이 증가
        self.decision_count_frame.pack_propagate(False)
        self.decision_count_var = tk.StringVar(value="0")
        self.decision_count_label = tk.Label(self.decision_count_frame, textvariable=self.decision_count_var,
                                             font=FONT_DECISION_COUNT_TEXT, fg=BOX_COUNT_TEXT_COLOR, bg=BOX_COUNT_BG_COLOR, anchor='center')
        self.decision_count_label.pack(expand=True, fill=tk.BOTH)

        # Betting Options Frame
        betting_frame = ttk.LabelFrame(left_panel, text="Betting Options", style='Info.TLabelframe', padding=10)
        betting_frame.pack(fill=tk.X, pady=(20,0), expand=False) # Increased pady for spacing

        self.large_bet_display_label = tk.Label(betting_frame, text=str(self.selected_bet.get()), font=(FONT_FAMILY_MAIN, 40, "bold"), bg=COLOR_CONTENT_BG, fg=COLOR_TEXT_DARK)
        self.large_bet_display_label.pack(pady=(5, 10))

        bet_values = [5, 10, 20, 30] # Updated bet values
        bet_radio_frame = ttk.Frame(betting_frame, style='InfoData.TFrame') # Using InfoData.TFrame for consistent background
        bet_radio_frame.pack(fill=tk.X, pady=(5,0))
        for val in bet_values:
            rb = ttk.Radiobutton(bet_radio_frame, text=str(val), variable=self.selected_bet, value=val, style='TRadiobutton')
            rb.pack(side=tk.LEFT, padx=10, expand=True) # Adjusted padx

        # self.current_bet_label = ttk.Label(betting_frame, text=f"Current Bet: {self.selected_bet.get()}", style='InfoData.TLabel', anchor='center') # Removed
        # self.current_bet_label.pack(pady=(8,5), fill=tk.X) # Removed

        self.selected_bet.trace_add('write', self._update_bet_display_label)

        # Signal Delay Frame
        delay_frame = ttk.LabelFrame(left_panel, text="Signal Display Delay (seconds)", style='Info.TLabelframe', padding=10)
        delay_frame.pack(fill=tk.X, pady=(15,0), expand=False) # Increased pady

        delay_values = [0, 3, 5, 10]
        delay_radio_frame = ttk.Frame(delay_frame, style='InfoData.TFrame') # Using InfoData.TFrame for consistent background
        delay_radio_frame.pack(fill=tk.X, pady=(5,5)) # Adjusted pady
        for val in delay_values:
            rb = ttk.Radiobutton(delay_radio_frame, text=str(val) + "s", variable=self.selected_delay, value=val, style='TRadiobutton')
            rb.pack(side=tk.LEFT, padx=10, expand=True) # Adjusted padx


        # 이동평균 정보 프레임 (이전과 유사)
        ma_info_frame = ttk.LabelFrame(left_panel, text="Moving Average Details", style='Info.TLabelframe', padding=10)
        ma_info_frame.pack(fill=tk.X, pady=(20,0), expand=False) # Increased pady for spacing
        ma5_frame = ttk.Frame(ma_info_frame, style='InfoData.TFrame')
        ma5_frame.pack(fill=tk.X, pady=3)
        ttk.Label(ma5_frame, text="MA(25s):", style='InfoData.TLabel').pack(side=tk.LEFT, padx=5) # 기간 표시
        self.ma5_value_label = ttk.Label(ma5_frame, text="-.--", style='InfoValue.TLabel')
        self.ma5_value_label.pack(side=tk.LEFT, padx=5)
        ttk.Label(ma5_frame, text="Slope:", style='InfoData.TLabel').pack(side=tk.LEFT, padx=5)
        self.ma5_slope_label = ttk.Label(ma5_frame, text="-.----", style='InfoValue.TLabel')
        self.ma5_slope_label.pack(side=tk.LEFT, padx=5)
        ma10_frame = ttk.Frame(ma_info_frame, style='InfoData.TFrame')
        ma10_frame.pack(fill=tk.X, pady=3)
        ttk.Label(ma10_frame, text="MA(50s):", style='InfoData.TLabel').pack(side=tk.LEFT, padx=5) # 기간 표시
        self.ma10_value_label = ttk.Label(ma10_frame, text="-.--", style='InfoValue.TLabel')
        self.ma10_value_label.pack(side=tk.LEFT, padx=5)
        ttk.Label(ma10_frame, text="Slope:", style='InfoData.TLabel').pack(side=tk.LEFT, padx=5)
        self.ma10_slope_label = ttk.Label(ma10_frame, text="-.----", style='InfoValue.TLabel')
        self.ma10_slope_label.pack(side=tk.LEFT, padx=5)


        # --- 오른쪽 패널 구성 (차트) ---
        # chart_card = ttk.Frame(right_panel, style='Card.TFrame', padding=5) # Commented out
        # chart_card.pack(fill=tk.BOTH, expand=True) # Commented out
        # self.fig = Figure(figsize=(6, 5), dpi=100, facecolor=COLOR_CONTENT_BG) # Commented out
        # self.ax = self.fig.add_subplot(111, facecolor="#e9ecef") # Commented out
        # self.ax.tick_params(axis='x', colors=COLOR_TEXT_DARK) # Commented out
        # self.ax.tick_params(axis='y', colors=COLOR_TEXT_DARK) # Commented out
        # self.ax.xaxis.label.set_color(COLOR_TEXT_DARK) # Commented out
        # self.ax.yaxis.label.set_color(COLOR_TEXT_DARK) # Commented out
        # self.ax.title.set_color(COLOR_TEXT_DARK) # Commented out
        # self.ax.spines['top'].set_visible(False); self.ax.spines['right'].set_visible(False) # Commented out
        # self.ax.spines['bottom'].set_color(COLOR_TEXT_SECONDARY); self.ax.spines['left'].set_color(COLOR_TEXT_SECONDARY) # Commented out
        # self.price_line, = self.ax.plot([], [], color=COLOR_TEXT_DARK, linestyle='-', linewidth=1.5, label='Price') # Commented out
        # self.ma5_line, = self.ax.plot([], [], color=BOX_UP_COLOR, linestyle='--', linewidth=1.5, label=f'MA({MA5_PERIOD*CANDLE_INTERVAL}s)') # Commented out
        # self.ma10_line, = self.ax.plot([], [], color=BOX_DOWN_COLOR, linestyle=':', linewidth=1.5, label=f'MA({MA10_PERIOD*CANDLE_INTERVAL}s)') # Commented out
        # legend = self.ax.legend(loc='best', frameon=False, fontsize=FONT_SIZE_XSMALL) # Commented out
        # for text in legend.get_texts(): text.set_color(COLOR_TEXT_DARK) # Commented out
        # self.ax.set_title('5s Candles & Moving Averages', fontdict={'family': FONT_FAMILY_MAIN, 'size':14, 'weight':'bold'}) # Commented out
        # self.ax.set_xlabel('Time (Candle Start)', fontdict={'family': FONT_FAMILY_MAIN, 'size':10}) # Commented out
        # self.ax.set_ylabel('Price', fontdict={'family': FONT_FAMILY_MAIN, 'size':10}) # Commented out
        # self.ax.grid(True, linestyle=':', alpha=0.5, color=COLOR_TEXT_SECONDARY) # Commented out
        # self.canvas = FigureCanvasTkAgg(self.fig, master=chart_card) # Commented out
        # self.canvas_widget = self.canvas.get_tk_widget() # Commented out
        # self.canvas_widget.pack(fill=tk.BOTH, expand=True) # Commented out
        # self.canvas.draw() # Commented out
        # self.fig.tight_layout(pad=1.0) # Commented out


        # 상태 표시줄
        status_frame = ttk.Frame(self.main_frame, padding=(0, 10, 0, 0))
        status_frame.pack(fill=tk.X)
        self.status_label = ttk.Label(status_frame, text="Initializing...", font=FONT_STATUS, foreground=COLOR_TEXT_SECONDARY, background=COLOR_PRIMARY_BG)
        self.status_label.pack(side=tk.LEFT)

        # self.ani = FuncAnimation(self.fig, self.update_chart, interval=1000, cache_frame_data=False) # Commented out
        self.start_countdown()

    def _update_bet_display_label(self, *args):
        if self.root.winfo_exists() and hasattr(self, 'large_bet_display_label'): # Check if label exists
            try:
                self.large_bet_display_label.config(text=str(self.selected_bet.get()))
            except tk.TclError as e:
                print(f"Error updating bet display label: {e}") # Log error if widget is destroyed

    def flash_signal_card(self):
        original_bg = str(self.signal_card.cget("bg")).lower() # 현재 배경색 저장 (소문자로)
        original_fg = str(self.signal_card.cget("fg")).lower()
        
        # 깜빡일 때 사용할 색상 (배경: 흰색, 글자: 원래 배경색과 유사한 어두운 색 또는 강조색)
        flash_bg_color = "#ffffff" 
        flash_fg_color = COLOR_TEXT_DARK # 기본적으로 어두운 텍스트

        # 원래 배경색이 UP 또는 DOWN일 경우, 깜빡일 때 텍스트 색상을 해당 신호색으로 유지해볼 수 있음
        if original_bg == BOX_UP_COLOR.lower():
            flash_fg_color = BOX_UP_COLOR
        elif original_bg == BOX_DOWN_COLOR.lower():
            flash_fg_color = BOX_DOWN_COLOR

        def flash_cycle(count):
            if not self.root.winfo_exists(): return
            
            current_bg_is_original = str(self.signal_card.cget("bg")).lower() == original_bg

            if current_bg_is_original:
                self.signal_card.config(bg=flash_bg_color, fg=flash_fg_color)
            else:
                self.signal_card.config(bg=original_bg, fg=original_fg) # 원래 색상으로 복원

            if count > 0:
                self.root.after(150, flash_cycle, count - 1)
            else: # 마지막에 반드시 원래 색상으로 복원
                self.signal_card.config(bg=original_bg, fg=original_fg)
        flash_cycle(6) # 3번 깜빡 (6단계)

    def start_countdown(self): # 이전과 동일
        self._update_countdown()

    def _update_countdown(self): # 이전과 동일
        if not self.root.winfo_exists(): return
        global countdown_seconds, last_decision_server_time_seconds
        if last_decision_server_time_seconds > 0 and DECISION_INTERVAL > 0:
            current_server_time_approx = int(time.time())
            next_decision_point = (int(last_decision_server_time_seconds / DECISION_INTERVAL) + 1) * DECISION_INTERVAL
            if current_server_time_approx > next_decision_point + DECISION_INTERVAL :
                current_block_end = (int(current_server_time_approx / DECISION_INTERVAL) + 1) * DECISION_INTERVAL
                countdown_seconds = max(0, current_block_end - current_server_time_approx)
            elif current_server_time_approx >= next_decision_point: countdown_seconds = 0
            else: countdown_seconds = max(0, next_decision_point - current_server_time_approx)
        else:
            current_local_time = int(time.time())
            if DECISION_INTERVAL > 0:
                start_of_current_minute_interval = int(current_local_time / DECISION_INTERVAL) * DECISION_INTERVAL
                elapsed_in_interval = current_local_time - start_of_current_minute_interval
                countdown_seconds = DECISION_INTERVAL - elapsed_in_interval
            else: countdown_seconds = 0
        try:
            if self.root.winfo_exists(): self.countdown_label.config(text=f"Next Signal In: {countdown_seconds}s")
        except tk.TclError: pass
        if self.root.winfo_exists(): self.root.after(1000, self._update_countdown)

    def change_symbol(self): # 이전과 동일 (dtype 부분 포함)
        global SYMBOL, ticker_df, candle_df, current_signal, last_decision_server_time_seconds, slope5, slope10, last_processed_event_time, decision_count, ticker_df_dtypes, candle_df_dtypes
        new_symbol = self.symbol_entry.get().lower()
        if new_symbol and new_symbol != SYMBOL:
            SYMBOL = new_symbol
            self.symbol_entry.delete(0, tk.END); self.symbol_entry.insert(0, SYMBOL.upper())
            print(f"UI: Symbol changed to {SYMBOL}.")
            ticker_df = pd.DataFrame(columns=list(ticker_df_dtypes.keys())).astype(ticker_df_dtypes)
            candle_df = pd.DataFrame(columns=list(candle_df_dtypes.keys())).astype(candle_df_dtypes)
            current_signal, slope5, slope10 = "FLAT", 0.0, 0.0
            last_decision_server_time_seconds, last_processed_event_time, decision_count = 0, 0, 0
            if self.root.winfo_exists():
                self.status_label.config(text=f"Switching to {SYMBOL.upper()}...")
                self.price_label.config(text="Current Price: $-.--")
                self.signal_card.config(text="WAITING...", bg=BOX_FLAT_COLOR, fg=COLOR_TEXT_LIGHT)
                self.time_label.config(text="Last Update: -")
                self.update_decision_time_display()
                self.update_decision_count_display()
                self.ma5_value_label.config(text="-.--"); self.ma5_slope_label.config(text="-.----")
                self.ma10_value_label.config(text="-.--"); self.ma10_slope_label.config(text="-.----")
                # self.price_line.set_data([], []); self.ma5_line.set_data([], []); self.ma10_line.set_data([], []) # Chart related
                # if self.ax: self.ax.relim(); self.ax.autoscale_view() # Chart related
                # if self.canvas: self.canvas.draw() # Chart related

    def update_price(self, price, event_time_ms): # 이전과 동일
        if not self.root.winfo_exists(): return
        try:
            self.price_label.config(text=f"Current Price: ${float(price):,.2f}")
            self.time_label.config(text=f"Last Update: {datetime.fromtimestamp(event_time_ms/1000).strftime('%H:%M:%S')}")
        except tk.TclError: pass

    def update_decision_time_display(self):
        if not self.root.winfo_exists(): return
        global last_decision_server_time_seconds, current_signal, decision_count # decision_count 추가

        bg_color = BOX_FLAT_COLOR # 기본색
        
        # 두 번째 결정부터 신호에 따른 색상 변경
        if decision_count >= 2:
            if current_signal == "UP": bg_color = BOX_UP_COLOR
            elif current_signal == "DOWN": bg_color = BOX_DOWN_COLOR
        # decision_count == 1 이거나, current_signal이 FLAT이면 BOX_FLAT_COLOR 유지

        self.decision_time_frame.config(bg=bg_color)
        self.decision_time_label.config(bg=bg_color, fg=COLOR_TEXT_LIGHT)

        if last_decision_server_time_seconds > 0:
            self.decision_time_label_var.set(datetime.fromtimestamp(last_decision_server_time_seconds).strftime('%H:%M:%S'))
        else:
            self.decision_time_label_var.set("--:--:--")
    def update_decision_count_display(self): # 이전과 동일
        if not self.root.winfo_exists(): return
        self.decision_count_var.set(str(decision_count))
        # Count 박스 배경은 고정 (BOX_COUNT_BG_COLOR)

    def update_signal(self, signal_to_display, ma5_val, ma10_val, ma5_slope_val, ma10_slope_val):
        if not self.root.winfo_exists(): return
        global decision_count # Ensure decision_count is accessible

        # Store all incoming signal data for potential delayed display
        self.pending_signal_data = {
            "signal": signal_to_display,
            "ma5_val": ma5_val,
            "ma10_val": ma10_val,
            "ma5_slope_val": ma5_slope_val,
            "ma10_slope_val": ma10_slope_val
        }

        try:
            # 1. Update MA values and slopes immediately
            self.ma5_value_label.config(text=f"{ma5_val:,.2f}" if not np.isnan(ma5_val) else "-.--")
            self.ma5_slope_label.config(text=f"{ma5_slope_val:.4f}" if not np.isnan(ma5_slope_val) else "-.----")
            self.ma10_value_label.config(text=f"{ma10_val:,.2f}" if not np.isnan(ma10_val) else "-.--")
            self.ma10_slope_label.config(text=f"{ma10_slope_val:.4f}" if not np.isnan(ma10_slope_val) else "-.----")

            # 2. Update decision count immediately
            self.update_decision_count_display() # This function reads global decision_count

            # 3. Cancel any existing delay timer
            if self.active_delay_timer:
                self.root.after_cancel(self.active_delay_timer)
                self.active_delay_timer = None

            delay_ms = self.selected_delay.get() * 1000

            if delay_ms == 0:
                # Call display_final_signal directly
                self.display_final_signal() # This method will be created in the next step
                self.active_delay_timer = None
            else:
                # Schedule display_final_signal and update signal card to a temporary state
                self.signal_card.config(text="DELAYED...", bg=BOX_FLAT_COLOR, fg=COLOR_TEXT_LIGHT) # Temporary state
                self.active_delay_timer = self.root.after(delay_ms, self.display_final_signal)

        except tk.TclError as e:
            print(f"Error in update_signal: {e}")
        except Exception as e: # Catch any other unexpected errors
            print(f"Unexpected error in update_signal: {e}")

    def display_final_signal(self):
        if not self.root.winfo_exists():
            return
        if self.pending_signal_data is None:
            print("display_final_signal called with no pending data.")
            return

        # These globals are read to determine UI behavior based on current state
        global decision_count, last_decision_server_time_seconds

        signal_to_display = self.pending_signal_data["signal"]
        # MA values are in self.pending_signal_data but not directly used in this method's logic for card/time display

        try:
            # Update Decision Time display (color and text)
            dt_bg_color = BOX_FLAT_COLOR
            if decision_count >= 2:
                if signal_to_display == "UP":
                    dt_bg_color = BOX_UP_COLOR
                elif signal_to_display == "DOWN":
                    dt_bg_color = BOX_DOWN_COLOR

            self.decision_time_frame.config(bg=dt_bg_color)
            self.decision_time_label.config(bg=dt_bg_color, fg=COLOR_TEXT_LIGHT)

            if last_decision_server_time_seconds > 0:
                self.decision_time_label_var.set(datetime.fromtimestamp(last_decision_server_time_seconds).strftime('%H:%M:%S'))
            else:
                self.decision_time_label_var.set("--:--:--")

            # Update Signal Card display (text and color)
            text_color = COLOR_TEXT_LIGHT
            if decision_count >= 2:
                if signal_to_display == "UP":
                    self.signal_card.config(text="↑ UP", bg=BOX_UP_COLOR, fg=text_color)
                elif signal_to_display == "DOWN":
                    self.signal_card.config(text="↓ DOWN", bg=BOX_DOWN_COLOR, fg=text_color)
                else: # FLAT
                    self.signal_card.config(text="FLAT", bg=BOX_FLAT_COLOR, fg=text_color)
            
            elif decision_count == 1:
                self.signal_card.config(text="ANALYZING...", bg=BOX_FLAT_COLOR, fg=COLOR_TEXT_LIGHT)

            else: # decision_count == 0
                 self.signal_card.config(text="WAITING...", bg=BOX_FLAT_COLOR, fg=COLOR_TEXT_LIGHT)

            self.active_delay_timer = None

        except tk.TclError as e:
            print(f"Error in display_final_signal (likely UI destroyed): {e}")
        except Exception as e:
            print(f"Unexpected error in display_final_signal: {e}")

    # def update_chart(self, frame): # Method Removed
    #     if not self.root.winfo_exists(): return
    #     if candle_df.empty:
    #         if self.ax: self.price_line.set_data([],[]); self.ma5_line.set_data([],[]); self.ma10_line.set_data([],[]); self.ax.relim(); self.ax.autoscale_view(tight=True)
    #         if self.canvas: self.canvas.draw()
    #         return
    #     try:
    #         timestamps_dt = [datetime.fromtimestamp(ts/1000) for ts in candle_df['candle_start_time']]
    #         self.price_line.set_data(timestamps_dt, candle_df['close'])
    #         if len(candle_df) >= MA5_PERIOD: self.ma5_line.set_data(timestamps_dt, candle_df['close'].rolling(window=MA5_PERIOD).mean())
    #         else: self.ma5_line.set_data([],[])
    #         if len(candle_df) >= MA10_PERIOD: self.ma10_line.set_data(timestamps_dt, candle_df['close'].rolling(window=MA10_PERIOD).mean())
    #         else: self.ma10_line.set_data([],[])
    #         self.ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M:%S'))
    #         self.ax.relim(); self.ax.autoscale_view(tight=True); self.fig.tight_layout(pad=1.0)
    #         self.canvas.draw()
    #     except Exception: pass


# --- 데이터 처리 및 웹소켓 로직 (이전과 동일) ---
def create_candle(app_instance, current_event_time_ms):
    global ticker_df, candle_df, last_decision_server_time_seconds, current_signal, slope5, slope10, decision_count
    candle_block_for_creation = int(current_event_time_ms / (CANDLE_INTERVAL * 1000)) -1
    candle_start_time_ms = candle_block_for_creation * (CANDLE_INTERVAL * 1000)
    candle_end_time_ms = candle_start_time_ms + (CANDLE_INTERVAL * 1000)
    ticks_for_candle = ticker_df[(ticker_df['event_time'] >= candle_start_time_ms) & (ticker_df['event_time'] < candle_end_time_ms)]
    if ticks_for_candle.empty: return
    new_candle_data = {'candle_start_time': candle_start_time_ms, 'open': ticks_for_candle['price'].iloc[0], 'high': ticks_for_candle['price'].max(), 'low': ticks_for_candle['price'].min(), 'close': ticks_for_candle['price'].iloc[-1]}
    if not candle_df.empty and candle_df['candle_start_time'].iloc[-1] == candle_start_time_ms: return
    candle_df = pd.concat([candle_df, pd.DataFrame([new_candle_data])], ignore_index=True)
    if len(candle_df) > WINDOW_SIZE: candle_df = candle_df.tail(WINDOW_SIZE).reset_index(drop=True)
    current_ma5, current_ma10, local_slope5, local_slope10 = np.nan, np.nan, 0.0, 0.0
    if len(candle_df) >= MA5_PERIOD:
        ma5_series = candle_df['close'].rolling(window=MA5_PERIOD).mean()
        current_ma5 = ma5_series.iloc[-1]
        if len(ma5_series.dropna()) >= SLOPE_PERIOD + 1 : local_slope5 = (ma5_series.iloc[-1] - ma5_series.iloc[-(SLOPE_PERIOD + 1)]) / SLOPE_PERIOD
    slope5 = local_slope5
    if len(candle_df) >= MA10_PERIOD:
        ma10_series = candle_df['close'].rolling(window=MA10_PERIOD).mean()
        current_ma10 = ma10_series.iloc[-1]
        if len(ma10_series.dropna()) >= SLOPE_PERIOD + 1: local_slope10 = (ma10_series.iloc[-1] - ma10_series.iloc[-(SLOPE_PERIOD + 1)]) / SLOPE_PERIOD
    slope10 = local_slope10
    if not (np.isnan(current_ma5) or np.isnan(current_ma10)):
        temp_signal = "FLAT"
        if slope5 > 0 and slope10 > 0: temp_signal = "UP"
        elif slope5 < 0 and slope10 < 0: temp_signal = "DOWN"
        decision_timestamp_seconds = candle_end_time_ms / 1000
# create_candle 함수 내 신호 확정 로직 수정

        if DECISION_INTERVAL > 0:
            current_decision_block_start = \
                int(decision_timestamp_seconds / DECISION_INTERVAL) * DECISION_INTERVAL

            previous_decision_block_start = 0
            if last_decision_server_time_seconds > 0:
                previous_decision_block_start = \
                    int(last_decision_server_time_seconds / DECISION_INTERVAL) * DECISION_INTERVAL
            
            if current_decision_block_start > previous_decision_block_start:
                
                # current_signal 업데이트는 항상 수행 (내부 상태 관리용)
                # 실제 UI 반영은 decision_count가 2 이상일 때 update_signal에서 처리
                previous_internal_signal = current_signal # UI 반영 전 내부 신호 변경 감지용
                current_signal = temp_signal 
                
                last_decision_server_time_seconds = current_decision_block_start 
                decision_count += 1 # decision_count는 여기서 증가
                
                # --- BEGIN NEW LOGGING CODE ---
                if previous_internal_signal != current_signal and decision_count >= 1: # Ensure it's a valid signal change
                    try:
                        with open(SIGNAL_LOG_FILE, "a", encoding="utf-8") as f:
                            log_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            f.write(f"[{log_timestamp}] Signal: {previous_internal_signal} -> {current_signal}\n")
                    except Exception as e:
                        print(f"Error writing to log file: {e}")
                # --- END NEW LOGGING CODE ---

                print(f"--- Internal Signal Update #{decision_count}: {current_signal} ---")
                print(f"Decision Time (Server): {datetime.fromtimestamp(last_decision_server_time_seconds).strftime('%H:%M:%S')}")
                # ... (기타 로그)
                print("-" * 40)

                # UI 업데이트는 app_instance.update_signal 호출 시 decision_count를 보고 결정
                if app_instance and app_instance.root and app_instance.root.winfo_exists():
                    # update_signal 함수로 현재 확정된 신호와 MA 값들을 전달
                    # update_signal 내부에서 decision_count를 확인하여 UI 반영 여부 결정
                    app_instance.root.after(0, app_instance.update_signal, 
                                            current_signal, current_ma5, current_ma10, 
                                            slope5, slope10) 
                    
                    # 깜빡임 효과 제거: 아래 라인 주석 처리 또는 삭제
                    # if previous_internal_signal != current_signal: # 내부 신호가 실제로 바뀌었을때만 고려
                    #     if decision_count >= 2: # 두 번째 신호부터 깜빡임 (이제 제거됨)
                    #          app_instance.root.after(0, lambda: app_instance.flash_signal_card())


    if len(ticker_df) > 300: ticker_df = ticker_df[ticker_df['event_time'] > candle_start_time_ms - (WINDOW_SIZE * CANDLE_INTERVAL * 1000 * 2)].reset_index(drop=True)

async def process_message(websocket, app_instance): # 이전과 동일
    global ticker_df, last_processed_event_time
    last_candle_creation_block = 0
    while True:
        if not app_instance.root.winfo_exists(): break
        try:
            message = await websocket.recv()
            data = json.loads(message)
            if 'e' in data and data['e'] == '24hrTicker' and 'E' in data and 'c' in data:
                event_time_ms, price = int(data['E']), float(data['c'])
                if event_time_ms <= last_processed_event_time: continue
                last_processed_event_time = event_time_ms
                ticker_df = pd.concat([ticker_df, pd.DataFrame([{'event_time': event_time_ms, 'price': price}])], ignore_index=True)
                if app_instance and app_instance.root: app_instance.root.after(0, app_instance.update_price, price, event_time_ms)
                current_time_block = int(event_time_ms / (CANDLE_INTERVAL * 1000))
                if current_time_block > last_candle_creation_block: create_candle(app_instance, event_time_ms); last_candle_creation_block = current_time_block
        except websockets.exceptions.ConnectionClosed: print("WS closed."); break
        except Exception as e: print(f"Msg err: {e}"); await asyncio.sleep(0.1)

async def ping_pong(websocket): # 이전과 동일
    while True:
        try: await websocket.ping(); await asyncio.sleep(20)
        except: break

_websocket_connection, _main_task_runner = None, None
async def main_inner(app_instance): # 이전과 동일 (dtype 부분 포함)
    global SYMBOL, ticker_df, candle_df, current_signal, slope5, slope10, last_decision_server_time_seconds, last_processed_event_time, decision_count, ticker_df_dtypes, candle_df_dtypes
    current_ws_url = f"wss://stream.binance.com:9443/ws/{SYMBOL.lower()}@ticker"
    if app_instance and app_instance.root and app_instance.root.winfo_exists():
        try: app_instance.status_label.config(text=f"Connecting to {SYMBOL.upper()}...")
        except: pass
    ticker_df = pd.DataFrame(columns=list(ticker_df_dtypes.keys())).astype(ticker_df_dtypes)
    candle_df = pd.DataFrame(columns=list(candle_df_dtypes.keys())).astype(candle_df_dtypes)
    current_signal, slope5, slope10 = "FLAT", 0.0, 0.0
    last_decision_server_time_seconds, last_processed_event_time, decision_count = 0, 0, 0
    if app_instance and app_instance.root and app_instance.root.winfo_exists():
        app_instance.root.after(0, app_instance.update_decision_time_display)
        app_instance.root.after(0, app_instance.update_decision_count_display)
        app_instance.root.after(0, app_instance.update_signal, "FLAT", np.nan, np.nan, 0.0, 0.0)
    try:
        async with websockets.connect(current_ws_url, ping_interval=None, ping_timeout=None) as websocket:
            _websocket_connection = websocket; print(f"WS connected: {current_ws_url}")
            if app_instance and app_instance.root and app_instance.root.winfo_exists():
                try: app_instance.status_label.config(text=f"{SYMBOL.upper()} stream active")
                except: pass
            tasks = [asyncio.create_task(ping_pong(websocket)), asyncio.create_task(process_message(websocket, app_instance))]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending: task.cancel()
            for task in done:
                if task.exception(): print(f"Task error: {task.exception()}")
    except Exception as e: print(f"WS main_inner err ({SYMBOL}): {e}")
    finally:
        if _websocket_connection and _websocket_connection.open:
            try: await _websocket_connection.close()
            except: pass
        print(f"main_inner for {SYMBOL} ended.")

async def main_manager(app_instance): # 이전과 동일
    global _main_task_runner, SYMBOL
    last_symbol_processed = None
    while True:
        if not app_instance.root.winfo_exists():
            if _main_task_runner and not _main_task_runner.done(): _main_task_runner.cancel()
            break
        current_ui_symbol = ""
        if app_instance.root.winfo_exists(): current_ui_symbol = app_instance.symbol_entry.get().lower()
        if current_ui_symbol != last_symbol_processed or (_main_task_runner and _main_task_runner.done()) or last_symbol_processed is None:
            if _main_task_runner and not _main_task_runner.done(): _main_task_runner.cancel()
            if current_ui_symbol and SYMBOL != current_ui_symbol: SYMBOL = current_ui_symbol
            if not SYMBOL:
                if app_instance.root.winfo_exists():
                    try: app_instance.status_label.config(text="Enter symbol.")
                    except: pass
                last_symbol_processed = None; await asyncio.sleep(1); continue
            print(f"Starting WS for: {SYMBOL.upper()}")
            _main_task_runner = asyncio.create_task(main_inner(app_instance))
            last_symbol_processed = SYMBOL
        await asyncio.sleep(1)
    if _main_task_runner and not _main_task_runner.done():
        try: await _main_task_runner
        except asyncio.CancelledError: pass # 이미 취소되었을 수 있음
    print("Main manager terminated.")

if __name__ == "__main__":
    try:
        with open(SIGNAL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Application started. Logging signals.\n")
    except Exception as e:
        print(f"Error initializing log file: {e}")

    root = tk.Tk()
    app = TradingSignalApp(root)
    threading.Thread(target=lambda: asyncio.run(main_manager(app)), daemon=True).start()
    try: root.mainloop()
    except KeyboardInterrupt: print("App interrupted.")
    finally: print("App closed.")