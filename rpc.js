var _rpc_calls = new Object;
var _rpc_id = 0;

// Don't use JSON.stringify, because it doesn't properly handle NaN and Infinity.
function _rpc_tojson (obj)
{
	if (typeof obj === 'object')
	{
		if (Boolean.prototype.isPrototypeOf (obj))
			obj = Boolean (obj);
		else if (Number.prototype.isPrototypeOf (obj))
			obj = Number (obj);
		else if (String.prototype.isPrototypeOf (obj))
			obj = String (obj);
	}
	if (typeof obj === 'number')
		return String (obj);
	else if (obj === undefined || obj === null || typeof obj === 'boolean' || typeof obj === 'string')
		return JSON.stringify (obj);
	else if (typeof obj === 'function')
		return undefined;
	else if (typeof obj === 'object')
	{
		if (Array.prototype.isPrototypeOf (obj))
		{
			var r = obj.reduce (function (prev, current, index, obj)
					{
						var c = _rpc_tojson (current);
						if (c === undefined)
							c = 'null';
						prev.push (c);
						return prev;
					}, []);
			return '[' + r.join (',') + ']';
		}
		var r = [];
		for (var a in obj)
		{
			var c = _rpc_tojson (obj[a]);
			if (c === undefined)
				continue;
			r.push (JSON.stringify (String (a)) + ':' + c);
		}
		return '{' + r.join (',') + '}';
	}
	alert ('unparsable object ' + String (obj) + ' passed to tojson');
	return undefined;
}

function Rpc (obj, onopen, onclose)
{
	var ret = #WEBSOCKET#;
	ret.onopen = onopen;
	ret.onclose = onclose;
	ret.onmessage = function (frame) { _rpc_message (ret, obj, frame.data); };
	ret.call = function (name, a, ka, reply)
	{
		var my_id;
		if (reply) {
			_rpc_id += 1;
			my_id = _rpc_id;
			_rpc_calls[my_id] = function (x) { delete _rpc_calls[my_id]; reply (x); };
		}
		else
			my_id = null;
		this.send (_rpc_tojson (['call', [my_id, name, a, ka]]));
	};
	ret.event = function (name, a, ka)
	{
		this.call (name, a, ka, null);
	};
	ret.multicall = function (args, cb, rets)
	{
		if (!rets)
			rets = [];
		if (args.length == 0) {
			if (cb)
				cb (rets);
			return;
		}
		var arg = args.shift ();
		this.call (arg[0], arg[1], arg[2], function (r) {
			rets.push (r);
			if (arg[3])
				arg[3] (r);
			ret.multicall (args, cb, rets);
		});
	};
	return ret;
}

function _rpc_message (websocket, obj, frame)
{
	// Don't use JSON.parse, because it cannot handle NaN and Infinity.
	var data = eval ('(' + frame + ')');
	var cmd = data[0];
	if (cmd == 'call')
	{
		try
		{
			var ret = obj[data[1][0]].apply (obj, data[1][1]);
			websocket.send (_rpc_tojson (['return', ret]));
		}
		catch (e)
		{
			websocket.send (_rpc_tojson (['error', e]));
		}
	}
	else if (cmd == 'event')
	{
		obj[data[1][0]].apply (obj, data[1][1]);
	}
	else if (cmd == 'error')
	{
		alert ('error: ' + data[1]);
	}
	else if (cmd == 'return')
	{
		_rpc_calls[data[1][0]] (data[1][1]);
	}
	else
	{
		alert ('unexpected command on websocket: ' + cmd);
	}
}
