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
    
    kana_dict = {}
    for _, row in df.iterrows():
        kana_dict[row['station1']] = row['station1_kana']
        kana_dict[row['station2']] = row['station2_kana']

    G_base = nx.MultiGraph() 
    for _, row in df.iterrows():
        G_base.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
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
        if key in line: color = val; break
    lbl = f"{line} [定期内]" if is_pass else line
    return f'<span style="background-color:{color}; color:white; padding:2px 6px; border-radius:3px; font-size:0.8em; font-weight:bold;">{lbl}</span>'

def format_route_html(path, G, pass_edges=set()):
    html = ""
    curr_line, seg_dist, seg_is_pass = None, 0.0, False
    first_st = path[0].split('_')[0]
    last_printed = first_st
    html += f"<b>{first_st}</b><br>"

    for i in range(len(path) - 1):
        u_node, v_node = path[i], path[i+1]
        u_st, v_st = u_node.split('_')[0], v_node.split('_')[0]
        edge = G[u_node][v_node]
        line, dist = edge.get('line', '不明'), edge.get('weight', 0.0)
        is_p = (tuple(sorted((u_st, v_st))) + (line,)) in pass_edges if pass_edges else edge.get('is_pass', False)

        if line == "同一駅":
            if curr_line:
                html += f" ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
                if last_printed != u_st: html += f"<b>{u_st}</b><br>"; last_printed = u_st
            if u_st != v_st:
                html += f" (同一駅扱い: {v_st}まで)<br><b>{v_st}</b><br>"
                last_printed = v_st
            curr_line, seg_dist, seg_is_pass = None, 0.0, False
            continue
        if curr_line is None: curr_line, seg_dist, seg_is_pass = line, dist, is_p
        elif line == curr_line and is_p == seg_is_pass: seg_dist += dist
        else:
            html += f" ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
            if last_printed != u_st: html += f"<b>{u_st}</b><br>"; last_printed = u_st
            curr_line, seg_dist, seg_is_pass = line, dist, is_p
            
    if curr_line: html += f" ↓ {line_tag(curr_line, seg_is_pass)} {seg_dist:.1f}km<br>"
    final_st = path[-1].split('_')[0]
    if last_printed != final_st: html += f"<b>{final_st}</b>"
    return html

try:
    G_base, G_recommend, G_fare_detail, all_stations, st_nodes, kana_dict = load_data()
    if "pass_edges" not in st.session_state: st.session_state.pass_edges = set()

    def format_search(s): return f"{s} | {kana_dict.get(s, '')}"
    def get_safe_idx(st_name, default=0): return all_stations.index(st_name) if st_name in all_stations else default

    # --- 定期管理 ---
    with st.expander(f"🎫 定期券の登録・管理 ({len(st.session_state.pass_edges)}区間登録中)"):
        c1, cv, c2 = st.columns(3)
        p_start = c1.selectbox("起点駅", all_stations, key="ps", index=get_safe_idx("池袋"), format_func=format_search)
        p_via = cv.selectbox("経由駅(任意)", ["なし"] + all_stations, key="pv", format_func=lambda x: x if x=="なし" else format_search(x))
        p_end = c2.selectbox("終点駅", all_stations, key="pe", index=get_safe_idx("渋谷", 1), format_func=format_search)
        
        route_preview = f"{p_start} ➔ {'(経由: ' + p_via + ') ➔ ' if p_via != 'なし' else ''}{p_end}"
        st.caption(f"📍 選択中の経路: {route_preview}")
        
        msg_slot = st.empty()
        if st.button("この区間を定期券として追加する", use_container_width=True, type="primary"):
            try:
                if p_start == p_end: msg_slot.warning("起点と終点が同じ駅です。")
                else:
                    if p_via == "なし": nodes = nx.shortest_path(G_base, p_start, p_end, weight='weight')
                    else: nodes = nx.shortest_path(G_base, p_start, p_via, weight='weight') + nx.shortest_path(G_base, p_via, p_end, weight='weight')[1:]
                    
                    for i in range(len(nodes)-1):
                        u, v = nodes[i], nodes[i+1]
                        edge_opts = G_base[u][v]
                        best_k = min(edge_opts, key=lambda k: edge_opts[k]['weight'])
                        st.session_state.pass_edges.add(tuple(sorted((u, v))) + (edge_opts[best_k]['line'],))
                    msg_slot.success(f"登録完了！")
                    st.rerun()
            except: msg_slot.error(f"経路が見つかりません。")

        if st.button("定期券データをリセット", type="secondary"):
            st.session_state.pass_edges = set(); st.rerun()

    st.divider()

    # --- ルート検索 ---
    st.markdown("### 🔍 運賃・経路検索")
    col1, col2 = st.columns(2)
    start_s = col1.selectbox("出発駅", all_stations, index=get_safe_idx("新宿三丁目"), format_func=format_search)
    end_s = col2.selectbox("到着駅", all_stations, index=get_safe_idx("上野"), format_func=format_search)

    if st.button("🔍 検索実行", use_container_width=True, type="primary"):
        if start_s == end_s: st.warning("出発駅と到着駅が同じです。")
        else:
            # 正規運賃
            dist_reg = nx.shortest_path_length(G_base, start_s, end_s, weight='weight')
            f_reg = get_fare_info(dist_reg)

            # 定期考慮
            G_fare_pass = G_fare_detail.copy()
            for u, v, data in G_fare_pass.edges(data=True):
                u_st, v_st = u.split('_')[0], v.split('_')[0]
                if (tuple(sorted((u_st, v_st))) + (data['line'],)) in st.session_state.pass_edges:
                    G_fare_pass[u][v]['weight'] = 0.0; G_fare_pass[u][v]['is_pass'] = True

            min_dist_eff, best_fare_path = float('inf'), []
            for sn in st_nodes[start_s]:
                for en in st_nodes[end_s]:
                    try:
                        d = nx.shortest_path_length(G_fare_pass, sn, en, weight='weight')
                        if d < min_dist_eff: min_dist_eff, best_fare_path = d, nx.shortest_path(G_fare_pass, sn, en, weight='weight')
                    except: continue
            
            f_eff = get_fare_info(min_dist_eff)
            
            # --- 運賃表示セクション ---
            st.markdown(f"### 💰 精算額: {f_eff['ta']}円")
            c1, c2 = st.columns(2)
            
            # きっぷ
            diff_t = f_eff['ta'] - f_reg['ta']
            c1.metric("きっぷ (大人)", f"{f_eff['ta']}円", f"{diff_t}円", delta_color="normal")
            c1.caption(f"小児: {f_eff['tc']}円 (通常:{f_reg['tc']}円)")
            
            # ICカード
            diff_i = f_eff['ia'] - f_reg['ia']
            c2.metric("ICカード (大人)", f"{f_eff['ia']}円", f"{diff_i}円", delta_color="normal")
            c2.caption(f"小児: {f_eff['ic']}円 (通常:{f_reg['ic']}円)")

            if diff_t < 0:
                st.success(f"🎊 定期券の利用で **{-diff_t}円** おトクになりました！")

            with st.expander("📝 運賃計算の根拠"):
                st.write(f"有効キロ程: {min_dist_eff:.1f} km / 正規キロ程: {dist_reg:.1f} km")
                st.markdown(format_route_html(best_fare_path, G_fare_pass), unsafe_allow_html=True)

            st.divider()
            st.markdown("### 🚶 おすすめルート")
            transfer_results = []
            for sn in st_nodes[start_s]:
                for en in st_nodes[end_s]:
                    try:
                        for p in nx.shortest_simple_paths(G_recommend, sn, en, weight='weight'):
                            tr = sum(1 for i in range(len(p)-1) if G_recommend[p[i]][p[i+1]]['line'] == "同一駅")
                            key = "->".join([node.split('_')[0] for node in p])
                            if not any(r['key'] == key for r in transfer_results):
                                transfer_results.append({'path': p, 'transfers': tr, 'key': key})
                            if len(transfer_results) > 5: break
                    except: continue
            
            for i, res in enumerate(sorted(transfer_results, key=lambda x: x['transfers'])[:5]):
                with st.container(border=True):
                    st.write(f"**ルート {i+1}** (乗り換え: {res['transfers']}回)")
                    st.markdown(format_route_html(res['path'], G_recommend, st.session_state.pass_edges), unsafe_allow_html=True)
except Exception as e: st.error(f"システムエラー: {e}")
