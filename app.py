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
    df = pd.read_csv('metrodata.csv')
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
                
    return G_base, G_transfer, sorted(list(station_to_lines.keys())), station_to_lines

def get_fare_info(distance):
    calc_km = math.ceil(distance)
    if calc_km == 0: return {"km": 0, "ta": 0, "tc": 0, "ia": 0, "ic": 0}
    tbl = [(6, 180, 90, 178, 89), (11, 210, 110, 209, 104), (19, 260, 130, 252, 126), 
           (27, 300, 150, 293, 146), (40, 330, 170, 324, 162), (float('inf'), 330, 170, 324, 162)]
    for l, ta, tc, ia, ic in tbl:
        if calc_km <= l: return {"km": calc_km, "ta": ta, "tc": tc, "ia": ia, "ic": ic}

def line_tag(line, is_pass=False):
    c = LINE_COLORS.get(line, "#888888")
    lbl = f"{line} [定期]" if is_pass else line
    return f'<span style="background-color:{c}; color:white; padding:2px 6px; border-radius:3px; font-size:0.8em; font-weight:bold;">{lbl}</span>'

# 経路を路線単位でHTML化する関数
def format_route_html(path, G, is_transfer_graph=False):
    html = ""
    curr_line = None
    seg_start = path[0].split('_')[0] if is_transfer_graph else path[0]
    seg_dist = 0.0

    for i in range(len(path) - 1):
        u, v = path[i], path[i+1]
        # MultiGraphと拡張Graphの両方に対応
        if is_transfer_graph:
            edge_data = G[u][v]
        else:
            # MultiGraphの場合は最適なエッジ(最短)を選ぶ
            edge_data = min(G[u][v].values(), key=lambda x: x['weight'])
            
        line, dist = edge_data['line'], edge_data['weight']
        is_pass_segment = (dist == 0 and not is_transfer_graph) # 定期考慮済みグラフなら0km

        if line == "同一駅":
            if curr_line:
                html += f"<b>{seg_start}</b><br> ↓ {line_tag(curr_line)} {seg_dist:.1f}km<br>"
            seg_start = v.split('_')[0] if is_transfer_graph else v
            curr_line, seg_dist = None, 0.0
            continue

        if curr_line is None:
            curr_line, seg_dist = line, dist
        elif line == curr_line:
            seg_dist += dist
        else:
            html += f"<b>{seg_start}</b><br> ↓ {line_tag(curr_line)} {seg_dist:.1f}km<br>"
            seg_start = u.split('_')[0] if is_transfer_graph else u
            curr_line, seg_dist = line, dist
            
    html += f"<b>{seg_start}</b><br> ↓ {line_tag(curr_line)} {seg_dist:.1f}km<br><b>{path[-1].split('_')[0]}</b>"
    return html

# --- 実行 ---
try:
    G_base, G_transfer, all_stations, station_to_lines = load_data()

    if "pass_edges" not in st.session_state: st.session_state.pass_edges = set()

    # --- 1. 定期券管理 (経由地指定対応) ---
    with st.expander(f"🎫 定期券の登録・管理 ({len(st.session_state.pass_edges)}区間)"):
        c1, cv, c2 = st.columns(3)
        p_start = c1.selectbox("起点", all_stations, key="ps")
        p_via = cv.selectbox("経由(任意)", ["なし"] + all_stations, key="pv")
        p_end = c2.selectbox("終点", all_stations, key="pe")
        
        if st.button("この経路を定期として登録", use_container_width=True):
            try:
                if p_via == "なし":
                    nodes = nx.shortest_path(G_base, p_start, p_end, weight='weight')
                else:
                    nodes = nx.shortest_path(G_base, p_start, p_via, weight='weight') + \
                            nx.shortest_path(G_base, p_via, p_end, weight='weight')[1:]
                
                for i in range(len(nodes)-1):
                    u, v = nodes[i], nodes[i+1]
                    best_line = min(G_base[u][v].items(), key=lambda x: x[1]['weight'])[1]['line']
                    st.session_state.pass_edges.add(tuple(sorted((u, v))) + (best_line,))
                st.success("定期券区間を更新しました。")
                st.rerun()
            except:
                st.error("経路が見つかりませんでした。")
            
        if st.button("定期券をすべてクリア", type="secondary"):
            st.session_state.pass_edges = set()
            st.rerun()

    st.divider()

    # --- 2. 検索 ---
    st.markdown("### 🔍 ルート検索")
    col1, col2 = st.columns(2)
    start = col1.selectbox("出発駅", all_stations, index=all_stations.index("新宿三丁目"))
    end = col2.selectbox("到着駅", all_stations, index=all_stations.index("上野"))

    if st.button("🔍 運賃・経路を検索", type="primary", use_container_width=True):
        # A. 運賃用グラフ構築
        G_fare = nx.Graph()
        for u, v, data in G_base.edges(data=True):
            is_pass = (tuple(sorted((u, v))) + (data['line'],)) in st.session_state.pass_edges
            w = 0.0 if is_pass else data['weight']
            if G_fare.has_edge(u, v):
                if w < G_fare[u][v]['weight']: G_fare.add_edge(u, v, weight=w, line=data['line'], is_pass=is_pass)
            else: G_fare.add_edge(u, v, weight=w, line=data['line'], is_pass=is_pass)
        
        dist_eff = nx.shortest_path_length(G_fare, start, end, weight='weight')
        f = get_fare_info(dist_eff)

        st.markdown(f"### 💰 精算額: {f['ta']}円")
        t1, t2 = st.columns(2)
        t1.metric("きっぷ (大人/小児)", f"{f['ta']}円", f"{f['tc']}円", delta_color="off")
        t2.metric("ICカード (大人/小児)", f"{f['ia']}円", f"{f['ic']}円", delta_color="off")
            
        with st.expander("📝 運賃計算の根拠を確認する"):
            path_f = nx.shortest_path(G_fare, start, end, weight='weight')
            # 運賃経路用のHTML表示（定期区間のバッジを出すために少し工夫）
            res_html = ""
            curr_l, s_start, s_dist, s_pass = None, path_f[0], 0.0, False
            for j in range(len(path_f)-1):
                u, v = path_f[j], path_f[j+1]
                e = G_fare[u][v]
                if curr_l is None:
                    curr_l, s_dist, s_pass = e['line'], e['weight'], e['is_pass']
                elif e['line'] == curr_l and e['is_pass'] == s_pass:
                    s_dist += e['weight']
                else:
                    res_html += f"<b>{s_start}</b><br> ↓ {line_tag(curr_l, s_pass)} {s_dist:.1f}km<br>"
                    s_start, curr_l, s_dist, s_pass = u, e['line'], e['weight'], e['is_pass']
            res_html += f"<b>{s_start}</b><br> ↓ {line_tag(curr_l, s_pass)} {s_dist:.1f}km<br><b>{path_f[-1]}</b>"
            st.markdown(res_html, unsafe_allow_html=True)

        st.divider()

        # B. 乗り換え案内
        st.markdown("### 🚶 おすすめの乗車ルート")
        transfer_results = []
        for sn in station_to_lines[start]:
            for en in station_to_lines[end]:
                for p in nx.shortest_simple_paths(G_transfer, sn, en, weight='weight'):
                    tr = sum(1 for i in range(len(p)-1) if G_transfer[p[i]][p[i+1]]['line'] == "同一駅")
                    path_key = "->".join([s.split('_')[0] for s in p])
                    if not any(r['key'] == path_key for r in transfer_results):
                        transfer_results.append({'path': p, 'transfers': tr, 'key': path_key})
                    if len(transfer_results) > 8: break
        
        for i, res in enumerate(sorted(transfer_results, key=lambda x: x['transfers'])[:5]):
            with st.container(border=True):
                st.write(f"**ルート {i+1}** (乗り換え: {res['transfers']}回)")
                st.markdown(format_route_html(res['path'], G_transfer, is_transfer_graph=True), unsafe_allow_html=True)

except Exception as e:
    st.error(f"エラー: {e}")
