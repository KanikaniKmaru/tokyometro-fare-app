import streamlit as st
import pandas as pd
import networkx as nx
import math

# 画面設定
st.set_page_config(page_title="メトロ運賃・定期案内プロ", page_icon="🚇", layout="centered")

# --- 設定・カラー ---
LINE_COLORS = {
    "銀座線": "#ff9500", "丸ノ内線": "#f62e36", "日比谷線": "#b5b5ac",
    "東西線": "#009bbf", "千代田線": "#00bb85", "有楽町線": "#c1a470",
    "半蔵門線": "#8f76d6", "南北線": "#00ac9b", "副都心線": "#9c5e31",
    "同一駅": "#333333"
}

@st.cache_data
def load_data():
    df = pd.read_csv('metrodata_kana.csv')
    
    # 読み方データは保持（将来用）
    kana_dict = {}
    for _, row in df.iterrows():
        kana_dict[row['station1']] = row['station1_kana']
        kana_dict[row['station2']] = row['station2_kana']
    
    G_base = nx.MultiGraph() 
    for _, row in df.iterrows():
        G_base.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
    G_transfer = nx.Graph()
    transfer_penalty = 10.0
    station_to_lines = {}
    for _, row in df.iterrows():
        s1, s2, dist, line = row['station1'], row['station2'], row['distance'], row['line']
        u, v = f"{s1}_{line}", f"{s2}_{line}"
        G_transfer.add_edge(u, v, weight=dist, line=line)
        for s in [s1, s2]:
            if s not in station_to_lines: station_to_lines[s] = []
            if f"{s}_{line}" not in station_to_lines[s]: station_to_lines[s].append(f"{s}_{line}")
    
    for s, nodes in station_to_lines.items():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                G_transfer.add_edge(nodes[i], nodes[j], weight=transfer_penalty, line="同一駅")
                
    return G_base, G_transfer, sorted(list(station_to_lines.keys())), station_to_lines, kana_dict

def get_fare_info(distance):
    calc_km = math.ceil(distance)
    if calc_km <= 0: return {"km": 0, "ta": 0, "tc": 0, "ia": 0, "ic": 0}
    tbl = [(6, 180, 90, 178, 89), (11, 210, 110, 209, 104), (19, 260, 130, 252, 126), 
           (27, 300, 150, 293, 146), (40, 330, 170, 324, 162), (float('inf'), 330, 170, 324, 162)]
    for l, ta, tc, ia, ic in tbl:
        if calc_km <= l: return {"km": calc_km, "ta": ta, "tc": tc, "ia": ia, "ic": ic}

def line_tag(line, is_pass=False):
    color = "#888888"
    for key, val in LINE_COLORS.items():
        if key in line:
            color = val
            break
    lbl = f"{line} [定期内]" if is_pass else line
    return f'<span style="background-color:{color}; color:white; padding:2px 6px; border-radius:3px; font-size:0.8em; font-weight:bold;">{lbl}</span>'

def format_route_html(path, G, is_transfer_graph=False):
    html = ""
    curr_line = None
    seg_start = path[0].split('_')[0] if is_transfer_graph else path[0]
    seg_dist = 0.0
    seg_is_pass = False

    for i in range(len(path) - 1):
        u, v = path[i], path[i+1]
        if is_transfer_graph:
            edge_data = G[u][v]
            line, dist, is_p = edge_data['line'], edge_data['weight'], False
        else:
            edge_data = G[u][v]
            line, dist, is_p = edge_data['line'], edge_data['weight'], edge_data.get('is_pass', False)

        if line == "同一駅":
            if curr_line:
                html += f"<b>{seg_start}</b><br> ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
            html += f"<b>{u.split('_')[0]}</b> (乗り換え)<br>"
            seg_start = v.split('_')[0] if is_transfer_graph else v
            curr_line, seg_dist, seg_is_pass = None, 0.0, False
            continue

        if curr_line is None:
            curr_line, seg_dist, seg_is_pass = line, dist, is_p
        elif line == curr_line and is_p == seg_is_pass:
            seg_dist += dist
        else:
            html += f"<b>{seg_start}</b><br> ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
            seg_start = u.split('_')[0] if is_transfer_graph else u
            curr_line, seg_dist, seg_is_pass = line, dist, is_p
            
    if curr_line:
        html += f"<b>{seg_start}</b><br> ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
    html += f"<b>{path[-1].split('_')[0]}</b>"
    return html

# --- 実行 ---
try:
    G_base, G_transfer, all_stations, station_to_lines, kana_dict = load_data()
    if "pass_edges" not in st.session_state: st.session_state.pass_edges = set()

    # 漢字のみを表示するように変更
    def format_station_minimal(s):
        return s

    # --- 定期管理 ---
    with st.expander(f"🎫 定期券の登録・管理 ({len(st.session_state.pass_edges)}区間)"):
        c1, cv, c2 = st.columns(3)
        p_start = c1.selectbox("起点", all_stations, key="ps", format_func=format_station_minimal)
        p_via = cv.selectbox("経由(任意)", ["なし"] + all_stations, key="pv", format_func=lambda x: x if x=="なし" else format_station_minimal(x))
        p_end = c2.selectbox("終点", all_stations, key="pe", format_func=format_station_minimal)
        msg_slot = st.empty()
        
        if st.button("この経路を定期として登録", use_container_width=True):
            try:
                if p_start == p_end:
                    msg_slot.warning("起点と終点が同じです。")
                else:
                    if p_via == "なし" or p_via == p_start or p_via == p_end:
                        nodes = nx.shortest_path(G_base, p_start, p_end, weight='weight')
                    else:
                        nodes = nx.shortest_path(G_base, p_start, p_via, weight='weight') + \
                                nx.shortest_path(G_base, p_via, p_end, weight='weight')[1:]
                    
                    for i in range(len(nodes)-1):
                        u, v = nodes[i], nodes[i+1]
                        edge_options = G_base[u][v]
                        best_key = min(edge_options, key=lambda k: edge_options[k]['weight'])
                        st.session_state.pass_edges.add(tuple(sorted((u, v))) + (edge_options[best_key]['line'],))
                    msg_slot.success("定期券区間を更新しました。")
                    st.rerun()
            except Exception:
                msg_slot.error(f"経路が見つかりませんでした。")

        if st.button("すべてクリア", type="secondary"):
            st.session_state.pass_edges = set()
            st.rerun()

    st.divider()

    # --- ルート検索 ---
    st.markdown("### 🔍 ルート検索")
    col1, col2 = st.columns(2)
    start_s = col1.selectbox("出発駅", all_stations, index=all_stations.index("新宿三丁目") if "新宿三丁目" in all_stations else 0, format_func=format_station_minimal)
    end_s = col2.selectbox("到着駅", all_stations, index=all_stations.index("上野") if "上野" in all_stations else 0, format_func=format_station_minimal)

    if st.button("🔍 運賃・経路を検索", type="primary", use_container_width=True):
        if start_s == end_s:
            st.warning("出発駅と到着駅が同じです。")
        else:
            dist_reg = nx.shortest_path_length(G_base, start_s, end_s, weight='weight')
            f_reg = get_fare_info(dist_reg)

            G_fare = nx.Graph()
            for u, v, key, data in G_base.edges(keys=True, data=True):
                is_p = (tuple(sorted((u, v))) + (data['line'],)) in st.session_state.pass_edges
                w = 0.0 if is_p else data['weight']
                if not
