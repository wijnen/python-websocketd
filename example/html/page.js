// This object is what connects us to the server.
var server;

// When the server makes a call to us, the corresponding function from this object is called.
var callbacks = {
	foo: function() {
		console.info('foo was called')
	},
	bar: function(arg) {
		console.info('bar was called, arg:', arg)
	}
};

// This function is called on startup, after the page is loaded.
window.AddEvent('load', function() {
	// Create server object. The arguments are:
	// callbacks: object with functions that can be called by the server.
	// onopen: function that will be called when the connection is established.
	// onclose: function that will be called when the connection failed to open, or is closed.
	server = Rpc(callbacks, onopen, onclose);
	// Nothing to do here, because the connection with the server is not yet established.
});

function onopen() {
	// We are connected to the server, show this to the user.
	document.getElementById('connected').checked = true;
	// Make some calls to the server right away.
	server.call('baz', ['my first arg', 2], {}, function(ret) { console.info('baz 1 returned', ret); });
	// Default arguments don't need to be passed.
	server.call('baz', ['my other first arg'], {}, function(ret) { console.info('baz 2 returned', ret); });
	// Named arguments can be used instead of positional arguments.
	server.call('baz', [], {arg1: 30, arg2: 'Hello!'}, function(ret) { console.info('baz 3 returned', ret); });
	// Positional and named arguments can be mixed.
	server.call('baz', [70], {arg2: 'Hi!'}, function(ret) { console.info('baz 4 returned', ret); });
	// If you don't need the return notification, the function and arguments can be omitted.
	server.call('baz', [7]);
	// Wait 10 seconds, then tell server to stop.
	setTimeout(function() { server.call('quit')}, 10000);
}

function onclose() {
	// We are no longer connected to the server, show this to the user.
	document.getElementById('connected').checked = false;
}
