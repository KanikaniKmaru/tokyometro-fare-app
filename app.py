import streamlit as st
import pandas as pd
import networkx as nx
import math

# 画面設定
st.set_page_config(page_title="メトロ運賃・乗換案内", page_icon="🚇", layout="centered")

# --- カラー設定 ---
LINE_COLORS = {
    "銀座線": "#ff9500",
    "丸ノ内線": "#f62e36",
    "日比谷線": "#b5b5ac",
    "東西線": "#009bbf",
    "千代田線": "#00bb85",
    "有楽町線": "#c1a470",
    "半蔵門線": "#8f76d6",
    "南北線": "#00ac9b",
    "副都心線": "#9c5e31",
    "同一駅": "#333333"
}

def get_color(line_name):
    for k, v in LINE_COLORS.items():
        if k in line_name: return v
    return "#888888" # デフォルト

# 路線ラベルをHTMLで生成
def line_label(line_name):
    color = get_color(line_name)
    return f'<span style="background-color:{color}; color:white; padding:2px 8px; border-radius:4px; font-weight:bold; font-size:0.8em; margin:0 5px;">{line_name}</span>'

# 1. データの読み込み
@st.cache_data
def load_data():
    df = pd.read_csv('metrodata.csv')
    G_fare = nx.Graph()
    for _, row in df.iterrows():
        G_fare.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
    G_transfer = nx.Graph()
    transfer_penalty = 10.0 
    stations = set()
    for _, row in df.iterrows():
        s1, s2, dist, line = row['station1'], row['station2'], row['distance'], row['line']
        u, v = f"{s1}_{line}", f"{s2}_{line}"
        G_transfer.add_edge(u, v, weight=dist, line=line)
        stations.add(s1); stations.add(s2)
        
    station_to_lines = {}
    for node in G_transfer.nodes:
        s, l = node.split('_')
        if s not in station_to_lines: station_to_lines[s] = []
        station_to_lines[s].append(node)
        
    for s, nodes in station_to_lines.items():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                G_transfer.add_edge(nodes[i], nodes[j], weight=transfer_penalty, line="同一駅")
    return G_fare, G_transfer, sorted(list(stations)), station_to_lines

# 経路をカラフルにまとめる
def get_summarized_route_html(path, G, is_transfer_graph=False):
    html = ""
    curr_line = None
    seg_start = path[0].split('_')[0] if is_transfer_graph else path[0]
    seg_dist = 0.0

    for i in range(len(path) - 1):
        u_name, v_name = path[i], path[i+1]
        edge = G[u_name][v_name]
        line, dist = edge['line'], edge['weight']
        
        if curr_line is None:
            curr_line, seg_dist = line, dist
        elif line == curr_line:
            seg_dist += dist
        else:
            html += f"<b>{seg_start}</b><br> ↓ {line_label(curr_line)} {seg_dist:.1f}km<br>"
            seg_start = u_name.split('_')[0] if is_transfer_graph else u_name
            curr_line, seg_dist = line, dist
            
    html += f"<b>{seg_start}</b><br> ↓ {line_label(curr_line)} {seg_dist:.1f}km<br><b>{path[-1].split('_')[0] if is_transfer_graph else path[-1]}</b>"
    return html

def get_fare_info(distance):
    calc_km = math.ceil(distance)
    table = [(6, 180, 90, 178, 89), (11, 210, 110, 209, 104), (19, 260, 130, 252, 126), (27, 300, 150, 293, 146), (40, 330, 170, 324, 162), (float('inf'), 330, 170, 324, 162)]
    for limit, t_a, t_c, ic_a, ic_c in table:
        if calc_km <= limit: return {"km": calc_km, "t_a": t_a, "t_c": t_c, "ic_a": ic_a, "ic_c": ic_c}

# --- アプリ本体 ---
st.markdown("<h2 style='text-align: center;'>🚇 東京メトロ 運賃案内</h2>", unsafe_allow_html=True)

try:
    G_fare, G_transfer, all_stations, station_to_lines = load_data()

    # スマートフォンで見やすいようメイン画面に配置
    st.write("🚉 **駅を選択してください**")
    col_s, col_e = st.columns(2)
    with col_s:
        start = st.selectbox("出発駅", all_stations, index=all_stations.index("新宿三丁目") if "新宿三丁目" in all_stations else 0)
    with col_e:
        end = st.selectbox("到着駅", all_stations, index=all_stations.index("上野") if "上野" in all_stations else 0)

    # 検索ボタン（ここを押すと計算開始）
    if st.button("🔍 運賃・経路を検索", type="primary", use_container_width=True):
        if start == end:
            st.warning("出発駅と到着駅が同じです。")
        else:
            total_dist = nx.shortest_path_length(G_fare, start, end, weight='weight')
            f = get_fare_info(total_dist)

            # 運賃結果
            st.markdown("### 💰 運賃")
            c1, c2 = st.columns(2)
            c1.metric("きっぷ（大人）", f"{f['t_a']}円")
            c2.metric("ICカード（大人）", f"{f['ic_a']}円")
            
            with st.expander("📝 運賃計算の根拠（最短経路）"):
                path_f = nx.shortest_path(G_fare, start, end, weight='weight')
                st.write(f"計算キロ程: {total_dist:.1f} km ({f['km']}km区分)")
                st.markdown(get_summarized_route_html(path_f, G_fare), unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### 🚶 おすすめの乗車ルート")
            
            # ルート検索
            results = []
            for sn in station_to_lines[start]:
                for en in station_to_lines[end]:
                    for p in nx.shortest_simple_paths(G_transfer, sn, en, weight='weight'):
                        transfers = sum(1 for i in range(len(p)-1) if G_transfer[p[i]][p[i+1]]['line'] == "同一駅")
                        path_key = "->".join([s.split('_')[0] for s in p])
                        if not any(r['key'] == path_key for r in results):
                            results.append({'key': path_key, 'path': p, 'transfers': transfers})
                        if len(results) > 8: break
            
            for i, res in enumerate(sorted(results, key=lambda x: x['transfers'])[:5]):
                with st.container(border=True):
                    st.write(f"**ルート {i+1}** (乗り換え: {res['transfers']}回)")
                    st.markdown(get_summarized_route_html(res['path'], G_transfer, is_transfer_graph=True), unsafe_allow_html=True)

except Exception as e:
    st.error(f"エラー: {e}")
