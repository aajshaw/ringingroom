from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from sassutils.wsgi import SassMiddleware
from random import sample
import re
import os

app = Flask(__name__, static_folder=os.path.join(os.getcwd(), 'static'))
app.config['SECRET_KEY'] = 's7WUt93.ir_bFya7'

socketio = SocketIO(app)

# set up automatic sass compilation
app.wsgi_app = SassMiddleware(app.wsgi_app, {
    'app': {
        'sass_path': 'static/sass',
        'css_path': 'static/css',
        'wsgi_path': 'static/css',
        'strip_extension': False
    }
})

# Keep track of towers


class Tower:
    def __init__(self, name, n=8):
        self._name = name
        self._n = 8
        self._bell_state = [True] * n
        self._audio = True

    @property
    def name(self):
        return(self._name)

    @name.setter
    def name(self, new_name):
        self._name = new_name

    @property
    def n_bells(self,):
        return(self._n)

    @n_bells.setter
    def n_bells(self, new_size):
        self._n = new_size
        self._bell_state = [True] * new_size

    @property
    def bell_state(self):
        return(self._bell_state)

    @bell_state.setter
    def bell_state(self, new_state):
        self._bell_state = new_state

    @property
    def audio(self):
        return('Tower' if self._audio else 'Hand')

    @audio.setter
    def audio(self, new_state):
        self._audio = True if new_state == 'Tower' else False


def clean_tower_name(name):
    out = re.sub(r'\s', '_', name)
    out = re.sub(r'\W', '', out)
    return out.lower()


def generate_random_change():
    # generate a random royal change, for use as uid
    return int(''.join(map(str, sample([i+1 for i in range(9)], k=9))))


towers = {}


# Serve the landing page
@app.route('/', methods=('GET', 'POST'))
def index():
    return render_template('landing_page.html')


@app.route('/<int:tower_id>/static/<path:path>')
def redirect_static(tower_id, path):
    return send_from_directory(app.static_folder, path)


#  Serve the static pages


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/help')
def help():
    return render_template('help.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/donate')
def donate():
    return render_template('donate.html')


# Create / find other towers/rooms
@app.route('/<int:tower_id>')
@app.route('/<int:tower_id>/<decorator>')
def tower(tower_id, decorator=None):
    return render_template('ringing_room.html',
                           tower_name=towers[tower_id].name)


# SocketIO Handlers


# The user entered a tower code on the landing page; check it
@socketio.on('c_check_tower_id')
def on_check_tower_id(json):
    global towers
    room_code = int(json['room_code'])
    if room_code in towers.keys():
        emit('s_check_id_success', {'tower_name': towers[room_code].name})
    else:
        emit('s_check_id_failure')


# The user entered a valid tower code and joined it
@socketio.on('c_join_tower_by_id')
def on_join_tower_by_id(json):
    tower_code = int(json['tower_code'])
    tower_name = towers[tower_code].name
    emit('s_redirection', str(tower_code) + '/' + clean_tower_name(tower_name))


# Create a new room with the user's name
@socketio.on('c_create_room')
def on_create_room(data):
    global towers
    global clean_tower_name

    room_name = data['room_name']
    new_room = Tower(room_name)
    new_uid = generate_random_change()
    towers[new_uid] = new_room
    emit('s_redirection', str(new_uid) + '/' + clean_tower_name(room_name))


# Join a room — happens on connection, but with more information passed
@socketio.on('c_join')
def on_join(json):
    tower_code = int(json['tower_code'])
    join_room(tower_code)
    emit('s_size_change', {'size': towers[tower_code].n_bells})
    emit('s_global_state', {'global_bell_state': towers[tower_code].bell_state})
    emit('s_name_change', {'new_name': towers[tower_code].name})
    emit('s_audio_change', {'new_audio': towers[tower_code].audio})


# A rope was pulled; ring the bell
@socketio.on('c_bell_rung')
def on_bell_rung(event_dict):
    cur_bell = event_dict["bell"]
    cur_room = int(event_dict["tower_code"])
    cur_tower = towers[cur_room]
    bell_state = cur_tower.bell_state
    if bell_state[cur_bell - 1] is event_dict["stroke"]:
        bell_state[cur_bell - 1] = not bell_state[cur_bell - 1]
    else:
        print('Current stroke disagrees between server and client')
    disagreement = True
    emit('s_bell_rung',
         {"global_bell_state": bell_state,
          "who_rang": cur_bell,
          "disagree": disagreement},
         broadcast=True, include_self=True, room=cur_room)


# A call was made
@socketio.on('c_call')
def on_call(call_dict):
    room = call_dict['room']
    emit('s_call', call_dict, broadcast=True,
         include_self=True, room=int(room))


# Tower size was changed
@socketio.on('c_size_change')
def on_size_change(size):
    room = int(size['room'])
    size = size['new_size']
    towers[room].n_bells = size
    emit('s_size_change', {'size': size},
         broadcast=True, include_self=True, room=room)
    emit('s_global_state', {'global_bell_state': towers[room].bell_state},
         broadcast=True, include_self=True, room=room)


# Audio type was changed
@socketio.on('c_audio_change')
def on_audio_change(json):
    room = int(json['room'])
    new_audio = 'Hand' if json['old_audio'] == 'Tower' else 'Tower'
    towers[room].audio = new_audio
    emit('s_audio_change', {'new_audio': new_audio},
         broadcast=True, include_self=True, room=room)


if __name__ == '__main__':
    socketio.run(app=app, host='0.0.0.0')
