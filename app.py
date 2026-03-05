import streamlit as st
import pandas as pd
import networkx as nx
import math

# 画面設定
st.set_page_config(page_title="メトロ運賃・定期券案内", page_icon="🚇", layout="centered")

# --- カラー設定 ---
LINE_COLORS = {
    "銀座線": "#ff9500", "丸ノ内線": "#f62e36", "日比谷線": "#b5b5ac",
    "東西線": "#009bbf", "千代田線": "#00bb85", "有楽町線": "#c1a470",
    "半蔵門線": "#8f76d6", "南北線": "#00ac9b", "副都心線": "#9c5e31",
    "同一駅": "#333333"
}

def get_color(line_name):
    for k, v in LINE_COLORS.items():
        if k in line_name: return v
    return "#888888"

def line_label(line_name, is_pass=False):
    color = "#cccccc" if is_pass else get_color(line_name)
    label = f"{line_name} [定期内]" if is_pass else line_name
    return f'<span style="background-color:{color}; color:white; padding:2px 8px; border-radius:4px; font-weight:bold; font-size:0.8em; margin:0 5px;">{label}</span>'

# 1. データの読み込み
@st.cache_data
def load_data():
    df = pd.read_csv('metrodata.csv')
    G_base = nx.MultiGraph() # 複数路線に対応
    stations = set()
    for _, row in df.iterrows():
        G_base.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
        stations.add(row['station1']); stations.add(row['station2'])
    return G_base, sorted(list(stations))

try:
    G_base, all_stations = load_data()

    # --- 定期券登録セクション ---
    if "pass_edges" not in st.session_state:
        st.session_state.pass_edges = [] # (u, v, line)

    st.markdown("### 🎫 定期券区間の登録")
    with st.expander("定期券区間を設定する（現在の登録: " + str(len(st.session_state.pass_edges)) + "区間）"):
        if not st.session_state.pass_edges:
            start_p = st.selectbox("定期券の起点駅を選択", all_stations, key="pass_start")
            if st.button("起点として設定"):
                st.session_state.pass_current_station = start_p
                st.session_state.pass_edges = [("__START__", start_p, "")]
                st.rerun()
        else:
            curr = st.session_state.pass_current_station
            st.info(f"現在の駅: **{curr}**")
            
            # 隣接駅のリスト作成
            options = []
            for n in G_base.neighbors(curr):
                for key in G_base[curr][n]:
                    line = G_base[curr][n][key]['line']
                    options.append(f"{n} ({line})")
            
            next_raw = st.selectbox("次の駅（路線）を選択", options)
            c1, c2 = st.columns(2)
            if c1.button("この区間を追加"):
                next_s = next_raw.split(" (")[0]
                line_s = next_raw.split(" (")[1].replace(")", "")
                st.session_state.pass_edges.append((curr, next_s, line_s))
                st.session_state.pass_current_station = next_s
                st.rerun()
            if c2.button("リセット", type="secondary"):
                st.session_state.pass_edges = []
                st.rerun()
            
            # 登録済み区間の表示
            st.write("現在のルート:")
            route_str = " ➔ ".join([e[1] for e in st.session_state.pass_edges])
            st.caption(route_str)

    st.divider()

    # --- 運賃・経路検索セクション ---
    st.markdown("### 🔍 運賃・経路検索")
    col_s, col_e = st.columns(2)
    start = col_s.selectbox("出発駅", all_stations, index=all_stations.index("新宿三丁目") if "新宿三丁目" in all_stations else 0)
    end = col_e.selectbox("到着駅", all_stations, index=all_stations.index("上野") if "上野" in all_stations else 0)

    if st.button("🔍 運賃・経路を検索", type="primary", use_container_width=True):
        if start == end:
            st.warning("出発駅と到着駅が同じです。")
        else:
            # 定期券を考慮したグラフの作成
            G_calc = nx.Graph()
            for u, v, data in G_base.edges(data=True):
                # 基本は元の距離
                w = data['weight']
                # 定期券に含まれるエッジなら距離を0にする
                for pu, pv, pline in st.session_state.pass_edges:
                    if ((u == pu and v == pv) or (u == pv and v == pu)) and data['line'] == pline:
                        w = 0.0
                # 最小距離のエッジを採用
                if G_calc.has_edge(u, v):
                    if w < G_calc[u][v]['weight']:
                        G_calc[u][v]['weight'] = w
                        G_calc[u][v]['line'] = data['line']
                else:
                    G_calc.add_edge(u, v, weight=w, line=data['line'])

            # 計算
            dist_outside = nx.shortest_path_length(G_calc, start, end, weight='weight')
            path = nx.shortest_path(G_calc, start, end, weight='weight')

            # 運賃表
            def get_fare(d):
                km = math.ceil(d)
                if km == 0: return {"km": 0, "t_a": 0, "ic_a": 0}
                tbl = [(6, 180, 178), (11, 210, 209), (19, 260, 252), (27, 300, 293), (40, 330, 324), (float('inf'), 330, 324)]
                for l, t, ic in tbl:
                    if km <= l: return {"km": km, "t_a": t, "ic_a": ic}

            f = get_fare(dist_outside)

            # 結果表示
            st.markdown(f"### 💰 定期精算額: {f['t_a']}円")
            st.caption(f"定期対象外キロ程: {dist_outside:.1f} km")

            st.markdown("### 🚶 おすすめルート")
            html = ""
            for i in range(len(path)-1):
                u, v = path[i], path[i+1]
                edge = G_calc[u][v]
                is_pass = (edge['weight'] == 0)
                html += f"<b>{u}</b><br> ↓ {line_label(edge['line'], is_pass)} {edge['weight']:.1f}km<br>"
            html += f"<b>{path[-1]}</b>"
            st.markdown(html, unsafe_allow_html=True)

except Exception as e:
    st.error(f"エラー: {e}")
