import streamlit as st
import pandas as pd
import networkx as nx
import math

# 画面設定
st.set_page_config(page_title="メトロ運賃・乗換案内", page_icon="🚇", layout="wide")
st.title("🚇 東京メトロ 運賃・乗り換え案内")

# 1. データの読み込みとグラフ構築
@st.cache_data
def load_data():
    df = pd.read_csv('metrodata.csv')
    
    # 運賃計算用（最短キロ程）
    G_fare = nx.Graph()
    for _, row in df.iterrows():
        G_fare.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
    # 乗り換え最小化用
    G_transfer = nx.Graph()
    transfer_penalty = 10.0 
    stations = set()
    for _, row in df.iterrows():
        s1, s2, dist, line = row['station1'], row['station2'], row['distance'], row['line']
        u, v = f"{s1}_{line}", f"{s2}_{line}"
        G_transfer.add_edge(u, v, weight=dist, line=line)
        stations.add(s1)
        stations.add(s2)
        
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

# 経路を路線ごとにまとめる関数
def get_summarized_route(path, G, is_transfer_graph=False):
    summary = []
    curr_line = None
    seg_start = path[0].split('_')[0] if is_transfer_graph else path[0]
    seg_dist = 0.0

    for i in range(len(path) - 1):
        u_name = path[i]
        v_name = path[i+1]
        edge = G[u_name][v_name]
        line = edge['line']
        dist = edge['weight']
        
        # 駅名の抽出
        v_station = v_name.split('_')[0] if is_transfer_graph else v_name

        if curr_line is None:
            curr_line = line
            seg_dist = dist
        elif line == curr_line:
            seg_dist += dist
        else:
            if seg_dist > 0 or curr_line == "同一駅":
                summary.append(f"**{seg_start}** ({curr_line} : {seg_dist:.1f}km) ")
            seg_start = u_name.split('_')[0] if is_transfer_graph else u_name
            curr_line = line
            seg_dist = dist
            
    summary.append(f"**{seg_start}** ({curr_line} : {seg_dist:.1f}km)  **{path[-1].split('_')[0] if is_transfer_graph else path[-1]}**")
    return " ➔ ".join(summary)

# 運賃計算関数
def get_fare_info(distance):
    calc_km = math.ceil(distance)
    # (距離上限, 切符大人, 切符小児, IC大人, IC小児)
    table = [
        (6, 180, 90, 178, 89),
        (11, 210, 110, 209, 104),
        (19, 260, 130, 252, 126),
        (27, 300, 150, 293, 146),
        (40, 330, 170, 324, 162),
        (float('inf'), 330, 170, 324, 162)
    ]
    for limit, t_a, t_c, ic_a, ic_c in table:
        if calc_km <= limit:
            return {"km": calc_km, "t_a": t_a, "t_c": t_c, "ic_a": ic_a, "ic_c": ic_c}

try:
    G_fare, G_transfer, all_stations, station_to_lines = load_data()

    # サイドバー入力
    with st.sidebar:
        st.header("🔍 経路検索")
        start = st.selectbox("出発駅", all_stations, index=all_stations.index("新宿三丁目") if "新宿三丁目" in all_stations else 0)
        end = st.selectbox("到着駅", all_stations, index=all_stations.index("上野") if "上野" in all_stations else 0)

    if start != end:
        # 運賃計算
        total_dist = nx.shortest_path_length(G_fare, start, end, weight='weight')
        f = get_fare_info(total_dist)

        # 運賃表示
        st.subheader("💰 運賃")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("きっぷ（大人）", f"{f['t_a']} 円")
            st.caption(f"小児: {f['t_c']} 円")
        with col2:
            st.metric("ICカード（大人）", f"{f['ic_a']} 円")
            st.caption(f"小児: {f['ic_c']} 円")

        # 運賃計算ルートの隠蔽表示
        with st.expander("📝 運賃計算の根拠（最短キロ程ルート）を確認する"):
            path_f = nx.shortest_path(G_fare, start, end, weight='weight')
            st.write(f"計算キロ程: **{total_dist:.1f} km** （{f['km']}km区分）")
            st.write(get_summarized_route(path_f, G_fare))

        st.divider()

        # 乗り換え最小ルート表示
        st.subheader("🚶 おすすめの乗車ルート（乗り換え回数順）")
        
        # 探索（上位5件）
        results = []
        for sn in station_to_lines[start]:
            for en in station_to_lines[end]:
                for p in nx.shortest_simple_paths(G_transfer, sn, en, weight='weight'):
                    # 乗り換え回数カウント
                    transfers = sum(1 for i in range(len(p)-1) if G_transfer[p[i]][p[i+1]]['line'] == "同一駅")
                    path_key = "->".join([s.split('_')[0] for s in p])
                    if not any(r['key'] == path_key for r in results):
                        results.append({'key': path_key, 'path': p, 'transfers': transfers})
                    if len(results) > 10: break
        
        # ソートして上位5つ
        for i, res in enumerate(sorted(results, key=lambda x: x['transfers'])[:5]):
            with st.container(border=True):
                st.write(f"**ルート {i+1}** (乗り換え: {res['transfers']}回)")
                st.write(get_summarized_route(res['path'], G_transfer, is_transfer_graph=True))

except Exception as e:
    st.error(f"エラー: {e}")
