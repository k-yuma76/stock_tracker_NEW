import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import os
import plotly.graph_objects as go
from datetime import datetime

# --- 1. ページ基本設定 ---
st.set_page_config(page_title="🇺🇸 トレンドトラッカー v6.9", layout="wide")
st.title("🇺🇸 トレンドトラッカー v6.9 🚀")

try:
    AV_API_KEY = st.secrets.get("AV_API_KEY", "")
except Exception:
    AV_API_KEY = ""

CACHE_FILE = "financial_data_cache.csv"

JP_NAME_DICT = {
    "MU": "マイクロン", "PL": "プラネット・ラボ", "TXN": "テキサス・インスツルメンツ",
    "NVDA": "エヌビディア", "TSLA": "テスラ", "OUST": "オースター",
    "AMD": "AMD", "INTC": "インテル", "RDW": "レッドワイヤー", "PLAB": "フォトトロニクス",
    "AXTI": "AXTインク", "WOLF": "ウルフスピード", "AEIS": "アドバンスト・エナジー",
    "IONQ": "IonQ", "RGTI": "リゲッティ", "QBTS": "D-Wave",
    "SOUN": "サウンドハウンドAI", "BBAI": "ビッグベア.ai", 
    "POWI": "パワー・インテグレーションズ", "BKSY": "ブラックスカイ",
    "NVT": "nVent(エヌベント)", "VRT": "バーティブ", "MOD": "モディーン", 
    "TT": "トレイン・テクノロジーズ", "AAON": "AAON"
}

# --- 2. 共通関数 ---
@st.cache_data
def load_themes_from_csv():
    csv_path = 'themes.csv'
    if not os.path.exists(csv_path): return {}, []
    try:
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.strip()
        if 'テーマ' not in df.columns or 'ティッカー' not in df.columns:
            if len(df.columns) >= 2: df.columns = ['テーマ', 'ティッカー'] + list(df.columns[2:])
            else: return {}, []
        df['テーマ'] = df['テーマ'].astype(str).str.strip()
        df['ティッカー'] = df['ティッカー'].astype(str).str.strip().str.upper()
        return df.groupby('テーマ')['ティッカー'].apply(list).to_dict(), df['ティッカー'].unique().tolist()
    except: return {}, []

themes, all_tickers = load_themes_from_csv()

def color_val(val):
    if pd.isna(val) or isinstance(val, str): return ''
    return 'color: #00C853; font-weight: bold;' if val > 0 else 'color: #FF5252; font-weight: bold;' if val < 0 else 'color: gray;'

def safe_float(val, default=None):
    try:
        if val in [None, "", "-", "None"]: return default
        f = float(val)
        return f if not pd.isna(f) else default
    except: return default

def format_large_number(num):
    if num is None or num == "N/A":
        return "N/A"
    try:
        num = float(num)
        if num == 0:
            return "$0"
        
        is_negative = num < 0
        abs_num = abs(num) # 絶対値にする
        
        if abs_num >= 1_000_000_000:
            formatted = f"${abs_num / 1_000_000_000:.2f}B"
        elif abs_num >= 1_000_000:
            formatted = f"${abs_num / 1_000_000:.2f}M"
        else:
            formatted = f"${abs_num:,.2f}"
            
        # マイナスだった場合は先頭に「-」をつける
        return f"-{formatted}" if is_negative else formatted
    except (ValueError, TypeError):
        return str(num)

# --- 時価総額の規模判定関数 ---
def get_mcap_category(mcap):
    if mcap is None or pd.isna(mcap):
        return ""
    try:
        mcap = float(mcap)
        if mcap >= 200_000_000_000:
            return " (超大型)"
        elif mcap >= 50_000_000_000:   
            return " (大型)"
        elif mcap >= 5_000_000_000:    
            return " (中型)"
        elif mcap >= 300_000_000:
            return " (小型)"
        else:
            return " (超小型)"
    except:
        return ""

def format_recommendation(rec_key):
    if not rec_key: return "データなし"
    rec_key = str(rec_key).lower()
    if "strong_buy" in rec_key: return "🟢 強い買い"
    if "buy" in rec_key: return "🟢 買い"
    if "hold" in rec_key: return "🟡 維持"
    if "sell" in rec_key: return "🔴 売り"
    return rec_key.capitalize()

# --- 3. キャッシュ管理 & データ取得 ---
def load_git_cache():
    if os.path.exists(CACHE_FILE):
        try: return pd.read_csv(CACHE_FILE, index_col=0).to_dict('index')
        except: return {}
    return {}

def save_git_cache(data_dict):
    try:
        df = pd.DataFrame.from_dict(data_dict, orient='index')
        df.to_csv(CACHE_FILE)
        return True
    except: return False

def get_comprehensive_info(t, api_key, force_update=False):
    p_cache = load_git_cache()
    if not force_update and t in p_cache:
        data = p_cache[t]
        data["source"] = "Git Cache (CSV)"
        return data

    data = {"ticker": t, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    try:
        info = yf.Ticker(t).info
        if info:
            cp = safe_float(info.get("currentPrice"), 999999)
            raw_f_eps = safe_float(info.get("forwardEps"))
            # 【重要】EPSが株価の半分を超える場合は異常値（株価の誤認）としてガード
            f_eps = raw_f_eps if raw_f_eps and raw_f_eps < (cp * 0.5) else safe_float(info.get("trailingEps"))
            
            data.update({
                "shares": info.get("sharesOutstanding"), "eps": info.get("trailingEps"),
                "f_eps": f_eps, "margin": info.get("operatingMargins"),
                "ebitda": info.get("ebitda"), "rev_growth": info.get("revenueGrowth"),
                "earn_growth": info.get("earningsGrowth"), "mcap_raw": info.get("marketCap"),
                "t_mean": info.get("targetMeanPrice"), "t_high": info.get("targetHighPrice"),
                "t_low": info.get("targetLowPrice"), "rec": info.get("recommendationKey"),
                "source": "Yahoo API"
            })
            if not force_update:
                p_cache[t] = data
                save_git_cache(p_cache)
    except: pass
    return data

# --- 4. サイドバー ---
with st.sidebar:
    st.write("## 🛠️ 管理機能")
    if st.button("🔄 全銘柄のデータを一括更新"):
        with st.status("データを一括取得中...", expanded=True) as status:
            new_cache = {}
            for t in all_tickers:
                st.write(f"取得中: {t}...")
                new_cache[t] = get_comprehensive_info(t, AV_API_KEY, force_update=True)
            if save_git_cache(new_cache):
                status.update(label="完了！Git Pushしてください。", state="complete")
    if st.button("🗑️ キャッシュ削除"):
        if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
        st.rerun()

# --- 5. メイン表示 ---
if themes:
    st.write("### 📅 トレンド集計期間")
    period_options = {"1日": 1, "1週": 5, "2週": 10, "1ヶ月": 30, "3ヶ月": 90}
    sel_p = st.radio("表示期間", list(period_options.keys()), horizontal=True, label_visibility="collapsed")
    days_back = period_options[sel_p]

    @st.cache_data(ttl=3600)
    def fetch_rankings(tickers, days):
        try:
            data = yf.download(tickers, period="6mo", progress=False)
            if data.empty: return pd.DataFrame()
            idx = -(days + 1) if len(data) > days else 0
            ret = ((data["Close"].iloc[-1] - data["Close"].iloc[idx]) / data["Close"].iloc[idx]) * 100
            vol = ((data["Volume"].iloc[-1] - data["Volume"].iloc[idx]) / data["Volume"].iloc[idx].replace(0, 1)) * 100
            return pd.DataFrame({"騰落率": ret, "出来高変化": vol}).dropna()
        except: return pd.DataFrame()

    results = fetch_rankings(all_tickers, days_back)

    if not results.empty:
        theme_summary = [{"テーマ": k, "平均騰落率": results.loc[[t for t in v if t in results.index], "騰落率"].mean(), "平均出来高変化": results.loc[[t for t in v if t in results.index], "出来高変化"].mean()} for k, v in themes.items()]
        df_theme = pd.DataFrame(theme_summary).sort_values("平均騰落率", ascending=False)

        st.write("### 🏆 セクター・ランキング")
        t_h = int(len(df_theme) * 35.5 + 38)
        sel_theme = st.dataframe(
            df_theme.style.map(color_val, subset=["平均騰落率", "平均出来高変化"]),
            column_config={
                "テーマ": st.column_config.TextColumn("テーマ名", width="medium"),
                "平均騰落率": st.column_config.NumberColumn("騰落率", format="%+.2f %%", width="small"),
                "平均出来高変化": st.column_config.NumberColumn("出来高", format="%+.1f %%", width="small")
            },
            height=t_h, on_select="rerun", selection_mode="single-row", hide_index=True
        )

        if sel_theme.selection.rows:
            t_name = df_theme.iloc[sel_theme.selection.rows[0]]["テーマ"]
            st.write(f"### 🔍 **{t_name}** の構成銘柄")
            t_list = [t for t in themes[t_name] if t in results.index]
            df_detail = results.loc[t_list].sort_values("騰落率", ascending=False).reset_index()
            df_detail.columns = ["銘柄", "騰落率", "出来高変化"]
            d_h = int(len(df_detail) * 35.5 + 38)
            sel_stock = st.dataframe(
                df_detail.style.map(color_val, subset=["騰落率", "出来高変化"]),
                column_config={
                    "銘柄": st.column_config.TextColumn("銘柄", width="small"),
                    "騰落率": st.column_config.NumberColumn("騰落率", format="%+.2f %%", width="small"),
                    "出来高変化": st.column_config.NumberColumn("出来高", format="%+.1f %%", width="small")
                },
                height=d_h, on_select="rerun", selection_mode="single-row", hide_index=True
            )

            if sel_stock.selection.rows:
                ticker = df_detail.iloc[sel_stock.selection.rows[0]]["銘柄"]
                st.markdown("---")
                st.write(f"### 📈 **{ticker}** ({JP_NAME_DICT.get(ticker, ticker)}) 総合分析")

                c_p = st.selectbox("チャート期間", ["1日", "1週間", "1ヶ月", "3ヶ月", "6ヶ月", "1年"], index=2)
                
                # --- 裏側で長めのデータを取得するように設定変更 ---
                p_map = {
                    "1日": ("5d", "5m"), 
                    "1週間": ("1mo", "60m"), 
                    "1ヶ月": ("1y", "1d"), 
                    "3ヶ月": ("1y", "1d"), 
                    "6ヶ月": ("2y", "1d"), 
                    "1年": ("2y", "1d")
                }
                f_p, y_i = p_map[c_p]

                info = get_comprehensive_info(ticker, AV_API_KEY)
                hist = yf.Ticker(ticker).history(period=f_p, interval=y_i)
                
                if not hist.empty:
                    # --- 1. 移動平均線の計算 (たっぷりの過去データを使って計算) ---
                    hist['SMA20'] = hist['Close'].rolling(window=20).mean()
                    hist['SMA50'] = hist['Close'].rolling(window=50).mean()

                    # --- 2. ユーザーが選んだ「表示期間」だけをハサミで切り出す ---
                    last_date = hist.index[-1]
                    if c_p == "1日":
                        hist = hist[hist.index.date == last_date.date()]
                    elif c_p == "1週間":
                        hist = hist[hist.index >= last_date - pd.Timedelta(days=7)]
                    elif c_p == "1ヶ月":
                        hist = hist[hist.index >= last_date - pd.DateOffset(months=1)]
                    elif c_p == "3ヶ月":
                        hist = hist[hist.index >= last_date - pd.DateOffset(months=3)]
                    elif c_p == "6ヶ月":
                        hist = hist[hist.index >= last_date - pd.DateOffset(months=6)]
                    elif c_p == "1年":
                        hist = hist[hist.index >= last_date - pd.DateOffset(years=1)]

                    if not hist.empty:
                        col1, col2 = st.columns([2, 1])
                        curr_val = hist['Close'].iloc[-1]
                        with col1:
                            # --- 【修正】showlegend=False を追加してローソク足の凡例を非表示 ---
                            fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], increasing_line_color='#00C853', decreasing_line_color='#FF5252', showlegend=False)])
                            
                            # --- 移動平均線の描画 ---
                            fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA20'], mode='lines', name='SMA 20 (短期)', line=dict(color='#29B6F6', width=1.5)))
                            fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA50'], mode='lines', name='SMA 50 (中期)', line=dict(color='#FFA726', width=1.5)))

                            breaks = [dict(bounds=["sat", "mon"])]
                            if y_i in ["5m", "60m"]: breaks.append(dict(bounds=[16, 9.5], pattern="hour"))
                            fig.update_xaxes(rangebreaks=breaks)
                            
                            max_v, min_v = hist['High'].max(), hist['Low'].min()
                            fig.add_annotation(x=hist['High'].idxmax(), y=max_v, text=f"高値: ${max_v:.2f}", showarrow=True, font=dict(color="#00C853"), bgcolor="rgba(0,0,0,0.6)")
                            fig.add_annotation(x=hist['Low'].idxmin(), y=min_v, text=f"安値: ${min_v:.2f}", showarrow=True, font=dict(color="#FF5252"), bgcolor="rgba(0,0,0,0.6)")
                            fig.add_annotation(x=hist.index[-1], y=curr_val, text=f"現在: ${curr_val:.2f}", showarrow=True, font=dict(color="white"), bgcolor="rgba(0,0,0,0.6)")
                            
                            y_margin_bottom = min_v * 0.15 
                            y_margin_top = max_v * 0.10    
                            y_min_padded = max(0, min_v - y_margin_bottom) 
                            y_max_padded = max_v + y_margin_top
                            
                            fig.update_layout(
                                height=480, 
                                margin=dict(l=10, r=10, t=30, b=10),
                                xaxis_rangeslider_visible=False,
                                yaxis=dict(range=[y_min_padded, y_max_padded], autorange=False),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        with col2:
                            st.write("#### 📊 業績 & 財務")
                            rev_g, earn_g = safe_float(info.get("rev_growth")), safe_float(info.get("earn_growth"))
                            
                            if rev_g is not None and earn_g is not None:
                                if rev_g > 0 and earn_g > 0: 
                                    st.success("業績トレンド: 🔥 上向き")
                                elif rev_g < 0 and earn_g < 0: 
                                    st.error("業績トレンド: 📉 下向き")
                                else:
                                    st.warning("業績トレンド: ⚖️ まちまち")
                            else:
                                st.info("業績トレンド: ➖ データなし")

                            st.info(f"推奨: **{format_recommendation(info.get('rec'))}**")
                            
                            t_mean = safe_float(info.get("t_mean"))
                            if t_mean:
                                st.write(f"- 平均目標株価: `${t_mean:.2f}` ({((t_mean-curr_val)/curr_val)*100:+.1f}%)")
                            
                            mcap_val = info.get('mcap_raw')
                            mcap_category = get_mcap_category(mcap_val)
                            st.write(f"- 時価総額: {format_large_number(mcap_val)}**{mcap_category}**")

                            st.write(f"- EBITDA: {format_large_number(info.get('ebitda'))}")
                            st.write(f"- 営業利益率: {safe_float(info.get('margin'), 0)*100:.1f}%")
                            
                            actual_eps = safe_float(info.get("eps"))
                            f_eps = safe_float(info.get("f_eps"))

                            st.write(f"- 実績 EPS (TTM): **{f'${actual_eps:.2f}' if actual_eps is not None else '-'}**")
                            if actual_eps is not None and actual_eps > 0:
                                st.write(f"- 実績 PER (TTM): **{(curr_val/actual_eps):.2f} 倍**")
                            else:
                                st.write("- 実績 PER (TTM): **-**")

                            st.write(f"- 予想 EPS (Forward): **{f'${f_eps:.2f}' if f_eps is not None else '-'}**")
                            if f_eps is not None and f_eps > 0:
                                st.write(f"- 予想 PER (Forward): **{(curr_val/f_eps):.2f} 倍**")
                            else:
                                st.write("- 予想 PER (Forward): **-**")
                            
                            st.markdown("---")
                            st.write("#### 💰 適正株価シミュレーター")
                            sim_eps = f_eps if f_eps is not None else 0
                            input_eps = st.number_input("予想EPS ($)", value=max(0.01, float(sim_eps)), step=0.1)
                            input_per = st.number_input("ターゲットPER", value=15.0, step=1.0)
                            fair_val = input_eps * input_per
                            st.metric("理論株価", f"${fair_val:.2f}", f"{((fair_val - curr_val) / curr_val) * 100:+.1f}%")
                            st.caption(f"ソース: {info.get('source', '不明')} / {info.get('updated_at', '-')}")