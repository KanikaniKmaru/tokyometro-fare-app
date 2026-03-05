import streamlit as st
import pandas as pd
import networkx as nx
import math

# 画面設定
st.set_page_config(page_title="メトロ運賃・乗換案内プロ", page_icon="🚇", layout="centered")

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
    G_base = nx.MultiGraph() # 同一区間の別路線を保持
    for _, row in df.iterrows():
        G_base.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
    # 乗り換え検索用の拡張グラフ（以前のロジック）
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
    # 距離上限, 切符大, 切符小, IC大, IC小
    tbl = [(6, 180, 90, 178, 89), (11, 210, 110, 209, 104), (19, 260, 130, 252, 126), 
           (27, 300, 150, 293, 146), (40, 330, 170, 324, 162), (float('inf'), 330, 170, 324, 162)]
    for l, ta, tc, ia, ic in tbl:
        if calc_km <= l: return {"km": calc_km, "ta": ta, "tc": tc, "ia": ia, "ic": ic}

def line_tag(line, is_pass=False):
    c = "#cccccc" if is_pass else LINE_COLORS.get(line, "#888888")
    lbl = f"{line} [定期]" if is_pass else line
    return f'<span style="background-color:{c}; color:white; padding:2px 6px; border-radius:3px; font-size:0.8em; font-weight:bold;">{lbl}</span>'

# --- 実行 ---
try:
    G_base, G_transfer, all_stations, station_to_lines = load_data()

    if "pass_edges" not in st.session_state: st.session_state.pass_edges = set()

    # --- 1. 定期券管理 (UI改善) ---
    with st.expander(f"🎫 定期券の登録・管理 ({len(st.session_state.pass_edges)}区間登録中)"):
        st.write("区間の端と端を選んで一気に登録できます")
        c1, c2 = st.columns(2)
        p_start = c1.selectbox("起点", all_stations, key="ps")
        p_end = c2.selectbox("終点", all_stations, key="pe")
        
        if st.button("この間の最短経路を定期として追加"):
            path = nx.shortest_path(G_base, p_start, p_end, weight='weight')
            for i in range(len(path)-1):
                # 複数路線のうち最短のものを採用
                u, v = path[i], path[i+1]
                best_line = min(G_base[u][v].items(), key=lambda x: x[1]['weight'])[1]['line']
                st.session_state.pass_edges.add(tuple(sorted((u, v))) + (best_line,))
            st.success("追加しました！")
            st.rerun()
            
        if st.button("定期券をすべてリセット", type="secondary"):
            st.session_state.pass_edges = set()
            st.rerun()

    st.divider()

    # --- 2. 検索 ---
    st.markdown("### 🔍 ルート検索")
    col1, col2 = st.columns(2)
    start = col1.selectbox("出発駅", all_stations, index=all_stations.index("新宿三丁目"))
    end = col2.selectbox("到着駅", all_stations, index=all_stations.index("上野"))

    if st.button("🔍 運賃・経路を検索", type="primary", use_container_width=True):
        # A. 運賃計算（定期考慮）
        G_fare = nx.Graph()
        for u, v, data in G_base.edges(data=True):
            w = 0.0 if (tuple(sorted((u, v))) + (data['line'],)) in st.session_state.pass_edges else data['weight']
            if G_fare.has_edge(u, v):
                if w < G_fare[u][v]['weight']: G_fare.add_edge(u, v, weight=w, line=data['line'])
            else: G_fare.add_edge(u, v, weight=w, line=data['line'])
        
        dist_eff = nx.shortest_path_length(G_fare, start, end, weight='weight')
        f = get_fare_info(dist_eff)

        # 運賃表示
        st.markdown(f"### 💰 精算額 (定期考慮済み)")
        t1, t2 = st.columns(2)
        with t1:
            st.write("**【きっぷ】**")
            st.metric("大人", f"{f['ta']}円")
            st.write(f"小児: {f['tc']}円")
        with t2:
            st.write("**【ICカード】**")
            st.metric("大人", f"{f['ia']}円")
            st.write(f"小児: {f['ic']}円")
            
        with st.expander("運賃計算の根拠"):
            path_f = nx.shortest_path(G_fare, start, end, weight='weight')
            res_html = ""
            for i in range(len(path_f)-1):
                u, v = path_f[i], path_f[i+1]
                e = G_fare[u][v]
                res_html += f"{u} <br> ↓ {line_tag(e['line'], e['weight']==0)} {e['weight']:.1f}km<br>"
            st.markdown(res_html + f"**{path_f[-1]}**", unsafe_allow_html=True)

        st.divider()

        # B. 乗り換え案内（従来どおり乗り換え回数優先）
        st.markdown("### 🚶 おすすめの乗り換えルート (回数順)")
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
                path = res['path']
                route_html = ""
                curr_l, s_start, s_dist = None, path[0].split('_')[0], 0.0
                for j in range(len(path)-1):
                    line = G_transfer[path[j]][path[j+1]]['line']
                    dist = G_transfer[path[j]][path[j+1]]['weight']
                    if line == "同一駅":
                        if curr_l: route_html += f"<b>{s_start}</b><br> ↓ {line_tag(curr_l)} {s_dist:.1f}km<br>"
                        curr_l, s_start, s_dist = None, path[j+1].split('_')[0], 0.0
                    else:
                        if curr_l is None: curr_l = line
                        s_dist += dist
                st.markdown(route_html + f"<b>{s_start}</b><br> ↓ {line_tag(curr_l)} {s_dist:.1f}km<br><b>{path[-1].split('_')[0]}</b>", unsafe_allow_html=True)

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
