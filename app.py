import streamlit as st
import pandas as pd
import networkx as nx
import math

# 画面設定
st.set_page_config(page_title="メトロ運賃・乗換案内カスタム", page_icon="🚇", layout="wide")
st.title("🚇 東京メトロ 運賃・乗り換え案内")

# 1. データの読み込みとグラフ構築
@st.cache_data
def load_data():
    df = pd.read_csv('metrodata.csv')
    
    # 運賃計算用（最短キロ程）
    G_fare = nx.Graph()
    for _, row in df.iterrows():
        G_fare.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
    # 乗り換え最小化用（拡張グラフ）
    # ノードを「駅名_路線名」にすることで乗り換えを表現する
    G_transfer = nx.Graph()
    transfer_penalty = 10.0 # 1回の乗り換えを10km分とみなしてペナルティを与える
    
    stations = set()
    for _, row in df.iterrows():
        s1, s2, dist, line = row['station1'], row['station2'], row['distance'], row['line']
        u, v = f"{s1}_{line}", f"{s2}_{line}"
        G_transfer.add_edge(u, v, weight=dist, line=line)
        stations.add(s1)
        stations.add(s2)
        
    # 同じ駅の異なる路線間を「乗り換えエッジ」で繋ぐ
    station_to_lines = {}
    for node in G_transfer.nodes:
        s, l = node.split('_')
        if s not in station_to_lines: station_to_lines[s] = []
        station_to_lines[s].append(node)
        
    for s, nodes in station_to_lines.items():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                G_transfer.add_edge(nodes[i], nodes[j], weight=transfer_penalty, line="乗り換え")

    all_stations = sorted(list(stations))
    return G_fare, G_transfer, all_stations, station_to_lines

try:
    G_fare, G_transfer, all_stations, station_to_lines = load_data()

    # 2. 入力エリア (st.selectboxは文字入力で検索可能)
    with st.sidebar:
        st.header("条件設定")
        start_station = st.selectbox("出発駅を選択（入力で検索）", all_stations, index=all_stations.index("新宿三丁目") if "新宿三丁目" in all_stations else 0)
        end_station = st.selectbox("到着駅を選択（入力で検索）", all_stations, index=all_stations.index("上野") if "上野" in all_stations else 0)
        st.caption("※駅名を入力すると候補が絞り込まれます")

    if start_station == end_station:
        st.warning("出発駅と到着駅が同じです。")
    else:
        # --- 運賃計算部分 ---
        dist_fare = nx.shortest_path_length(G_fare, source=start_station, target=end_station, weight='weight')
        calc_km = math.ceil(dist_fare)
        fares = [(6, 180), (11, 210), (19, 260), (27, 300), (float('inf'), 330)]
        fare = next(f for k, f in fares if calc_km <= k)

        st.subheader(f"運賃: {fare}円")
        st.write(f"（最短計算キロ程: {dist_fare:.1f} km / 区分: {calc_km} km）")

        with st.expander("🔍 運賃計算の根拠となる最短経路を確認する"):
            path_fare = nx.shortest_path(G_fare, source=start_station, target=end_station, weight='weight')
            st.write("メトロのルール上、以下の最短ルートで計算されています：")
            st.write(" → ".join(path_fare))

        st.divider()

        # --- 乗り換え最小ルート検索（上位5つ） ---
        st.subheader("🚶 おすすめの乗車ルート（乗り換えが少ない順）")
        
        # 拡張グラフ上での全ての開始・終了ノード候補
        start_nodes = station_to_lines[start_station]
        end_nodes = station_to_lines[end_station]
        
        # 最短経路を複数探す
        all_paths = []
        for sn in start_nodes:
            for en in end_nodes:
                # k-shortest paths を取得
                generator = nx.shortest_simple_paths(G_transfer, source=sn, target=en, weight='weight')
                count = 0
                for p in generator:
                    all_paths.append(p)
                    count += 1
                    if count >= 3: break # 各組み合わせから上位3つ

        # 全ての候補を乗り換え回数と距離でソート
        unique_results = []
        seen_paths = set()
        
        for p in all_paths:
            # 路線情報の抽出と乗り換え回数の計算
            route_steps = []
            transfers = 0
            total_d = 0
            for i in range(len(p)-1):
                edge = G_transfer[p[i]][p[j := i+1]]
                line = edge['line']
                dist = edge['weight']
                if line == "乗り換え":
                    transfers += 1
                else:
                    total_d += dist
                route_steps.append({'from': p[i].split('_')[0], 'to': p[j].split('_')[0], 'line': line, 'dist': dist})
            
            # まとめて表示するための処理
            path_str = "->".join([s.split('_')[0] for s in p])
            if path_str not in seen_paths:
                unique_results.append({'transfers': transfers, 'distance': total_d, 'steps': route_steps, 'path_key': path_str})
                seen_paths.add(path_str)

        # 乗り換え回数 -> 距離 の順でソートして上位5つを表示
        sorted_results = sorted(unique_results, key=lambda x: (x['transfers'], x['distance']))[:5]

        for i, res in enumerate(sorted_results):
            with st.container(border=True):
                col1, col2 = st.columns([1, 4])
                col1.metric(f"ルート {i+1}", f"{res['transfers']}回")
                with col2:
                    st.write(f"**総距離: {res['distance']:.1f} km**")
                    # 表示のグループ化
                    display_text = []
                    curr_line = None
                    s_start = res['steps'][0]['from']
                    s_dist = 0
                    for step in res['steps']:
                        if step['line'] == "乗り換え":
                            if curr_line:
                                display_text.append(f"{s_start} --[{curr_line}]--> {step['from']}")
                            curr_line = None
                            s_start = step['to']
                        else:
                            if curr_line is None:
                                curr_line = step['line']
                                s_start = step['from']
                                s_dist = step['dist']
                            elif curr_line == step['line']:
                                s_dist += step['dist']
                            else:
                                display_text.append(f"{s_start} --[{curr_line}]--> {step['from']}")
                                curr_line = step['line']
                                s_start = step['from']
                                s_dist = step['dist']
                    if curr_line:
                        display_text.append(f"{s_start} --[{curr_line}]--> {res['steps'][-1]['to']}")
                    
                    st.write(" ➔ ".join(display_text))

except Exception as e:
    st.error(f"エラーが発生しました。データを確認してください: {e}")
