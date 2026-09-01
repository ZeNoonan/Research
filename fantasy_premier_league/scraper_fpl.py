import requests
import json
import time
import pandas as pd

# where to dump the csvs
OUT = 'data/2026-27/'
# OUT = 'C:/Users/Darragh/Documents/Python/premier_league/'

data = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/')
data = json.loads(data.content)

names = pd.DataFrame(data['elements']).apply(pd.Series)
teams = {t['id']: t['name'] for t in data['teams']}

names['full_name'] = (names['first_name'] + '_' + names['second_name']).str.lower()
names['Position'] = names['element_type'].map({1: 'GK', 2: 'DF', 3: 'MD', 4: 'FW'})
names['team_name'] = names['team'].map(teams)

# one call per player - element-summary gives every gameweek he has played
rows = []
for player_id, full_name, position, team in zip(
        names['id'], names['full_name'], names['Position'], names['team_name']):
    player = requests.get(
        'https://fantasy.premierleague.com/api/element-summary/' + str(player_id) + '/')
    player = json.loads(player.content)
    for gw in player['history']:
        gw['full_name'] = full_name
        gw['Position'] = position
        gw['team'] = team
        rows.append(gw)
    print(player_id, full_name)
    time.sleep(0.2)

gw_data = pd.DataFrame(rows)
gw_data['Price'] = gw_data['value'] / 10
gw_data['opponent_team'] = gw_data['opponent_team'].map(teams)

cols_to_move = ['full_name', 'team', 'Position', 'Price', 'round',
                'opponent_team', 'was_home', 'minutes', 'total_points']
cols = cols_to_move + [col for col in gw_data if col not in cols_to_move]
gw_data = gw_data[cols]

gw_data.to_csv(OUT + 'all_gws.csv', index=False)
print('all_gws.csv', len(gw_data))

for gw, week in gw_data.groupby('round'):
    week.to_csv(OUT + 'gw' + str(gw) + '.csv', index=False)
    print('gw' + str(gw) + '.csv', len(week))
