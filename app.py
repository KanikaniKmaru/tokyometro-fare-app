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

    # 1. 定期登録用：駅名をノードにした基本グラフ (MultiGraph)
    G_base = nx.MultiGraph() 
    for _, row in df.iterrows():
        G_base.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
    # 2. 経路表示・乗り換え検索用：(駅_路線) をノードにした詳細グラフ
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
        # 同一駅内の乗り換えエッジを追加
        for s, nodes in station_to_nodes.items():
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    G.add_edge(nodes[i], nodes[j], weight=penalty, line="同一駅")
        return G, station_to_nodes

    G_recommend, st_nodes = build_transfer_graph(10.0) # 乗り換えペナルティあり
    G_fare_detail, _ = build_transfer_graph(0.0)    # 運賃根拠用（ペナルティなし）
                
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

# 改良版：駅名の重複を防ぎ、乗り換えを美しく表示するHTML生成器
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
        u_st = u_node.split('_')[0]
        v_st = v_node.split('_')[0]
        
        edge = G[u_node][v_node]
        line = edge.get('line', '不明')
        dist = edge.get('weight', 0.0)
        # 定期判定
        is_p = False
        if not pass_edges:
            is_p = edge.get('is_pass', False)
        else:
            is_p = (tuple(sorted((u_st, v_st))) + (line,)) in pass_edges

        if line == "同一駅":
            if curr_line:
                html += f" ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
                if last_printed != u_st:
                    html += f"<b>{u_st}</b><br>"
                    last_printed = u_st
            
            label = "(改札内乗り換え)" if u_st == v_st else f"(徒歩で {v_st} へ移動)"
            html += f" {label}<br>"
            if last_printed != v_st:
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

# --- アプリ実行 ---
try:
    G_base, G_recommend, G_fare_detail, all_stations, st_nodes, kana_dict = load_data()
    if "pass_edges" not in st.session_state: st.session_state.pass_edges = set()

    def format_search(s):
        return f"{s} | {kana_dict.get(s, '')}"

    # --- 定期管理 ---
    with st.expander(f"🎫 定期券の登録・管理 ({len(st.session_state.pass_edges)}区間)"):
        c1, cv, c2 = st.columns(3)
        p_start = c1.selectbox("起点", all_stations, key="ps", format_func=format_search)
        p_via = cv.selectbox("経由(任意)", ["なし"] + all_stations, key="pv", format_func=lambda x: x if x=="なし" else format_search(x))
        p_end = c2.selectbox("終点", all_stations, key="pe", format_func=format_search)
        msg_slot = st.empty()
        
        if st.button("この経路を定期として登録", use_container_width=True):
            try:
                if p_start == p_end:
                    msg_slot.warning("起点と終点が同じ駅です。")
                else:
                    if p_via == "なし":
                        nodes = nx.shortest_path(G_base, p_start, p_end, weight='weight')
                    else:
                        nodes = nx.shortest_path(G_base, p_start, p_via, weight='weight') + nx.shortest_path(G_base, p_via, p_end, weight='weight')[1:]
                    
                    for i in range(len(nodes)-1):
                        u, v = nodes[i], nodes[i+1]
                        edge_options = G_base[u][v]
                        # MultiGraph対応のインデックス取得
                        best_key = min(edge_options, key=lambda k: edge_options[k]['weight'])
                        line_name = edge_options[best_key]['line']
                        st.session_state.pass_edges.add(tuple(sorted((u, v))) + (line_name,))
                    msg_slot.success("定期券区間を正常に更新しました！")
                    st.rerun()
            except nx.NetworkXNoPath:
                msg_slot.error(f"経路が見つかりませんでした。データを確認してください。")
            except Exception as e:
                msg_slot.error(f"エラーが発生しました: {e}")

        if st.button("すべてクリア", type="secondary"):
            st.session_state.pass_edges = set()
            st.rerun()

    st.divider()

    # --- ルート検索 ---
    st.markdown("### 🔍 ルート検索")
    col1, col2 = st.columns(2)
    start_s = col1.selectbox("出発駅", all_stations, index=all_stations.index("新宿三丁目") if "新宿三丁目" in all_stations else 0, format_func=format_search)
    end_s = col2.selectbox("到着駅", all_stations, index=all_stations.index("上野") if "上野" in all_stations else 0, format_func=format_search)

    if st.button("🔍 運賃・経路を検索", type="primary", use_container_width=True):
        if start_s == end_s:
            st.warning("出発駅と到着駅が同じです。")
        else:
            # 1. 正規運賃
            dist_reg = nx.shortest_path_length(G_base, start_s, end_s, weight='weight')
            f_reg = get_fare_info(dist_reg)

            # 2. 定期考慮グラフ構築 (詳細グラフをベースにする)
            G_fare_pass = G_fare_detail.copy()
            for u, v, data in G_fare_pass.edges(data=True):
                u_st, v_st = u.split('_')[0], v.split('_')[0]
                is_p = (tuple(sorted((u_st, v_st))) + (data['line'],)) in st.session_state.pass_edges
                if is_p:
                    G_fare_pass[u][v]['weight'] = 0.0
                    G_fare_pass[u][v]['is_pass'] = True

            # 運賃計算 (全路線入り口候補から探索)
            min_dist_eff = float('inf')
            best_fare_path = []
            for sn in st_nodes[start_s]:
                for en in st_nodes[end_s]:
                    try:
                        d = nx.shortest_path_length(G_fare_pass, sn, en, weight='weight')
                        if d < min_dist_eff:
                            min_dist_eff = d
                            best_fare_path = nx.shortest_path(G_fare_pass, sn, en, weight='weight')
                    except: continue
            
            f_eff = get_fare_info(min_dist_eff)

            # 表示
            st.markdown(f"### 💰 精算額: {f_eff['ta']}円")
            c1, c2 = st.columns(2)
            diff_t = f_eff['ta'] - f_reg['ta']
            c1.metric("きっぷ (大人)", f"{f_eff['ta']}円", f"{diff_t}円")
            diff_i = f_eff['ia'] - f_reg['ia']
            c2.metric("ICカード (大人)", f"{f_eff['ia']}円", f"{diff_i}円")

            if diff_t < 0:
                st.success(f"定期券の利用により合計 **{-diff_t}円** 安くなりました！")

            with st.expander("📝 運賃計算の根拠（最短経路）"):
                st.write(f"有効キロ程: {min_dist_eff:.1f} km / 正規キロ程: {dist_reg:.1f} km")
                st.markdown(format_route_html(best_fare_path, G_fare_pass), unsafe_allow_
