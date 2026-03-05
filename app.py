import streamlit as st
import pandas as pd
import networkx as nx
import math

# 画面設定
st.set_page_config(page_title="メトロ運賃・定期案内", page_icon="🚇", layout="centered")

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
    df['station1'] = df['station1'].str.strip()
    df['station2'] = df['station2'].str.strip()
    
    # 読み方辞書
    kana_dict = {}
    for _, row in df.iterrows():
        kana_dict[row['station1']] = row['station1_kana']
        kana_dict[row['station2']] = row['station2_kana']

    # 1. 定期登録用：駅名をノードにした基本グラフ
    G_base = nx.MultiGraph() 
    for _, row in df.iterrows():
        G_base.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
    # 2. 経路表示・乗り換え検索用詳細グラフ
    def build_transfer_graph(penalty):
        G = nx.Graph()
        station_to_nodes = {}
        for _, row in df.iterrows():
            s1, s2, d, l = row['station1'], row['station2'], row['distance'], row['line']
            u, v = f"{s1}_{l}", f"{s2}_{l}"
            G.add_edge(u, v, weight=d, line=l)
            for s in [s1, s2]:
                if s not in station_to_nodes: station_to_nodes[s] = []
                if f"{s}_{l}" not in station_to_nodes[s]: station_to_nodes[s].append(f"{s}_{l}")
        for s, nodes in station_to_nodes.items():
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    G.add_edge(nodes[i], nodes[j], weight=penalty, line="同一駅")
        return G, station_to_nodes

    G_recommend, st_nodes = build_transfer_graph(10.0)
    G_fare_detail, _ = build_transfer_graph(0.0)    
                
    return G_base, G_recommend, G_fare_detail, sorted(list(st_nodes.keys())), st_nodes, kana_dict

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

# 改良版：駅名の重複を削り、(同一駅扱い) を表示するHTML
def format_route_html(path, G, pass_edges=set()):
    html = ""
    curr_line = None
    seg_dist = 0.0
    seg_is_pass = False
    
    first_station = path[0].split('_')[0]
    last_printed = first_station
    html += f"<b>{first_station}</b><br>"

    for i in range(len(path) - 1):
        u_node, v_node = path[i], path[i+1]
        u_st, v_st = u_node.split('_')[0], v_node.split('_')[0]
        
        edge = G[u_node][v_node]
        line = edge.get('line', '不明')
        dist = edge.get('weight', 0.0)
        
        # 定期判定
        is_p = False
        if pass_edges:
            is_p = (tuple(sorted((u_st, v_st))) + (line,)) in pass_edges
        else:
            is_p = edge.get('is_pass', False)

        if line == "同一駅":
            if curr_line:
                html += f" ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
                if last_printed != u_st:
                    html += f"<b>{u_st}</b><br>"
                    last_printed = u_st
            
            # 同一駅名（改札内）なら何も表示せず次へ
            # 駅名が違う場合（溜池山王-国会議事堂前など）のみ「同一駅扱い」を表示
            if u_st != v_st:
                html += f" (同一駅扱い: {v_st}まで)<br>"
                html += f"<b>{v_st}</b><br>"
                last_printed = v_st
            
            curr_line, seg_dist, seg_is_pass = None, 0.0, False
            continue

        if curr_line is None:
            curr_line, seg_dist, seg_is_pass = line, dist, is_p
        elif line == curr_line and is_p == seg_is_pass:
            seg_dist += dist
        else:
            html += f" ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
            if last_printed != u_st:
                html += f"<b>{u_st}</b><br>"
                last_printed = u_st
            curr_line, seg_dist, seg_is_pass = line, dist, is_p
            
    if curr_line:
        html += f" ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
    
    final_st = path[-1].split('_')[0]
    if last_printed != final_st:
        html += f"<b>{final_st}</b>"
    
    return html

# --- 実行 ---
try:
    G_base, G_recommend, G_fare_detail, all_stations, st_nodes, kana_dict = load_data()
    if "pass_edges" not in st.session_state: st.session_state.pass_edges = set()

    def format_search(s):
        return f"{s} | {kana_dict.get(s, '')}"

    # --- 定期管理 ---
    with st.expander(f"🎫 定期券の登録・管理 ({len(st.session_state
