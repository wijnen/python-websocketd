// vim: set foldmethod=marker :
var _rpc_calls = new Object;
var _rpc_id = 0;
var _rpc_queue = [];
var _rpc_busy = 0;

// Don't use JSON.stringify, because it doesn't properly handle NaN and Infinity.
function _rpc_tojson(obj) { // {{{
	if (typeof obj === 'object') {
		if (Boolean.prototype.isPrototypeOf(obj))
			obj = Boolean(obj);
		else if (Number.prototype.isPrototypeOf(obj))
			obj = Number(obj);
		else if (String.prototype.isPrototypeOf(obj))
			obj = String(obj);
	}
	if (typeof obj === 'number')
		return String(obj);
	else if (obj === undefined || obj === null || typeof obj === 'boolean' || typeof obj === 'string')
		return JSON.stringify(obj);
	else if (typeof obj === 'function')
		return undefined;
	else if (typeof obj === 'object') {
		if (Array.prototype.isPrototypeOf(obj)) {
			var r = obj.reduce(function(prev, current, index, obj) {
						var c = _rpc_tojson(current);
						if (c === undefined)
							c = 'null';
						prev.push(c);
						return prev;
					}, []);
			return '[' + r.join(',') + ']';
		}
		var r = [];
		for (var a in obj) {
			var c = _rpc_tojson(obj[a]);
			if (c === undefined)
				continue;
			r.push(JSON.stringify(String(a)) + ':' + c);
		}
		return '{' + r.join(',') + '}';
	}
	alert('unparsable object ' + String(obj) + ' passed to tojson');
	return undefined;
} // }}}

function Rpc(obj, onopen, onclose) { // {{{
	var _rpc_process = function() {
		var sem = _rpc_busy++;
		if (sem) {
			--_rpc_busy;
			setTimeout(_rpc_process, 10);
			return;
		}
		while (_rpc_queue.length > 0) {
			_rpc_message(ws, obj, _rpc_queue.shift().data);
		}
		--_rpc_busy;
	};
	var proto = document.location.protocol;
	var wproto = proto[proto.length - 2] == 's' ? 'wss:' : 'ws:';
	var slash = document.location.pathname[document.location.pathname.length - 1] == '/' ? '' : '/';
	var target = wproto + document.location.host + document.location.pathname + slash + 'websocket/' + document.location.search;
	var ws = new WebSocket(target);
	var ret = { _websocket: ws };
	ws.onopen = onopen;
	ws.onclose = onclose;
	ws.onmessage = function(frame) {
		_rpc_queue.push(frame);
		setTimeout(_rpc_process, 0);
	}
	ret.call = function(name, a, ka, reply) {
		if (a === undefined)
			a = [];
		if (ka === undefined)
			ka = {};
		var my_id;
		if (reply) {
			_rpc_id += 1;
			my_id = _rpc_id;
			_rpc_calls[my_id] = function(x) { delete _rpc_calls[my_id]; reply(x); };
		}
		else
			my_id = null;
		ws.send(_rpc_tojson(['call', [my_id, name, a, ka]]));
	};
	ret.event = function(name, a, ka) {
		this.call(name, a, ka, null);
	};
	ret.multicall = function(args, cb, rets, from) {
		if (!rets)
			rets = [];
		if (!from)
			from = 0;
		if (from >= args.length) {
			if (cb)
				cb(rets);
			return;
		}
		var arg = args[from];
		this.call(arg[0], arg[1], arg[2], function(r) {
			rets.push(r);
			if (arg[3])
				arg[3] (r);
			ret.multicall(args, cb, rets, from + 1);
		});
	};
	ret.proxy = new Proxy(ret, { get: function(target, name) {
		return function() {
			var args = [];
			for (var i = 0; i < arguments.length; ++i)
				args.push(arguments[i]);
			ret.call(name, args, {}, null);
		};
	}});
	return ret;
} // }}}

function _rpc_message(websocket, obj, frame) { // {{{
	// Don't use JSON.parse, because it cannot handle NaN and Infinity.
	// eval seems like a security risk, but it isn't because the data
	// and this file come from the same server; if it is compromised,
	// it will just send malicious data directly.
	var data = eval('(' + frame + ')');
	var cmd = data[0];
	if (cmd == 'call') {
		try {
			var id = data[1][0];
			var ret;
			if (data[1][1] in obj)
				ret = obj[data[1][1]].apply(obj, data[1][2]);
			else if ('' in obj)
				ret = obj[''].apply(obj, [data[1][1]].concat(data[1][2]));
			else
				console.warn('Warning: undefined function ' + data[1][1] + ' called, but no default callback defined');
			if (id != null)
				websocket.send(_rpc_tojson(['return', [id, ret]]));
		}
		catch (e) {
			console.error('call returns error', e);
			if (id != null)
				websocket.send(_rpc_tojson(['error', e]));
		}
	}
	else if (cmd == 'error') {
		alert('error: ' + data[1]);
	}
	else if (cmd == 'return') {
		_rpc_calls[data[1][0]] (data[1][1]);
	}
	else {
		alert('unexpected command on websocket: ' + cmd);
	}
} // }}}
