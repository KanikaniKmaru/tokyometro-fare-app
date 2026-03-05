import streamlit as st
import pandas as pd
import networkx as nx
import math

# 画面設定
st.set_page_config(page_title="俺専用・メトロ運賃案内", page_icon="🚇")
st.title("🚇 東京メトロ 最短キロ程・運賃検索")
st.caption("東京メトロの運賃計算に使われる、出発駅から到着駅までの最短経路を調べます")

# 1. データの読み込み
@st.cache_data # データをキャッシュして高速化
def load_data():
    df = pd.read_csv('metrodata.csv')
    G = nx.Graph()
    for _, row in df.iterrows():
        G.add_edge(row['station1'], row['station2'], weight=row['distance'], line=row['line'])
    
    # 全駅のリスト（セレクトボックス用）
    all_stations = sorted(list(set(df['station1']) | set(df['station2'])))
    return G, all_stations

try:
    G, stations = load_data()

    # 2. 入力エリア
    col1, col2 = st.columns(2)
    with col1:
        start = st.selectbox("出発駅", stations, index=stations.index("新宿三丁目") if "新宿三丁目" in stations else 0)
    with col2:
        goal = st.selectbox("到着駅", stations, index=stations.index("上野") if "上野" in stations else 0)

    if st.button("運賃を計算する", type="primary"):
        # 計算ロジック
        path = nx.shortest_path(G, source=start, target=goal, weight='weight')
        total_dist = nx.shortest_path_length(G, source=start, target=goal, weight='weight')
        
        # 運賃判定
        calc_km = math.ceil(total_dist)
        fares = [(6, 180), (11, 210), (19, 260), (27, 300), (float('inf'), 330)]
        fare = next(f for k, f in fares if calc_km <= k)

        # 結果表示
        st.divider()
        st.metric(label="適用運賃", value=f"{fare} 円")
        st.info(f"合計キロ程: {total_dist:.1f} km （運賃区分: {calc_km} km）")

        # ルート表示
        st.subheader("📍 最短経路（路線別まとめ）")
        current_line, segment_start, segment_dist = None, path[0], 0.0
        
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            line, dist = G[u][v]['line'], G[u][v]['weight']
            if current_line is None:
                current_line, segment_dist = line, dist
            elif line == current_line:
                segment_dist += dist
            else:
                st.write(f"**{segment_start}** → ({current_line} : {segment_dist:.1f}km) → **{u}**")
                segment_start, current_line, segment_dist = u, line, dist
        st.write(f"**{segment_start}** → ({current_line} : {segment_dist:.1f}km) → **{path[-1]}**")

except Exception as e:

    st.error(f"エラーが発生しました: {e}")

