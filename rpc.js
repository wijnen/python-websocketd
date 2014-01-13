var _rpc_reply;

function Rpc (obj, onopen, onclose)
{
	var ret = #WEBSOCKET#;
	ret.onopen = onopen;
	ret.onclose = onclose;
	ret.onmessage = function (frame) { _rpc_message (ret, obj, frame.data); };
	ret.call = function (name, a, ka, reply)
	{
		_rpc_reply = reply;
		this.send (JSON.stringify (['call', [name, a, ka]]));
	};
	ret.event = function (name, a, ka)
	{
		this.send (JSON.stringify (['event', [name, a, ka]]));
	};
	return ret;
}

function _rpc_message (websocket, obj, frame)
{
	data = JSON.parse (frame);
	cmd = data[0];
	if (cmd == 'call')
	{
		try
		{
			var ret = obj[data[1][0]].apply (obj, data[1][1]);
			websocket.send (JSON.stringify (['return', ret]));
		}
		catch (e)
		{
			websocket.send (JSON.stringify (['error', e]));
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
		if (_rpc_reply)
			_rpc_reply (data[1]);
		else
			alert ('received return without making a call');
	}
	else
	{
		alert ('unexpected command on websocket: ' + cmd);
	}
}
