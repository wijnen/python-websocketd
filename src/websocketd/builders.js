"use strict";

// Creating and managing elements and their properties. {{{

// Create a new element and return it. Optionally give it a class.
function Create(name, className) { // {{{
	return document.createElement(name).AddClass(className);
} // }}}

// Add a child element and return it (for inline chaining). Optionally give it a class.
Object.defineProperty(Object.prototype, 'Add', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(object, className) {
		if (!(object instanceof Array))
			object = [object];
		for (var i = 0; i < object.length; ++i) {
			if (typeof object[i] == 'string')
				this.AddText(object[i]);
			else {
				this.appendChild(object[i]);
				object[i].AddClass(className);
			}
		}
		return object[0];
	}
}); // }}}

// Create a new element and add it as a child. Return the new element (for inline chaining).
Object.defineProperty(Object.prototype, 'AddElement', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(name, className) {
		var element = document.createElement(name);
		return this.Add(element, className);
	}
}); // }}}

// Add a child text node and return the element (not the text).
Object.defineProperty(Object.prototype, 'AddText', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(text) {
		var t = document.createTextNode(text);
		this.Add(t);
		return this;
	}
}); // }}}

// Remove all child elements.
Object.defineProperty(Object.prototype, 'ClearAll', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function() {
		while (this.firstChild)
			this.removeChild(this.firstChild);
		return this;
	}
}); // }}}

// Add a class to an element. Keep all existing classes. Return the element for inline chaining.
Object.defineProperty(Object.prototype, 'AddClass', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(className) {
		if (!className)
			return this;
		var classes = this.className.split(' ');
		var newclasses = className.split(' ');
		for (var i = 0; i < newclasses.length; ++i) {
			if (newclasses[i] && classes.indexOf(newclasses[i]) < 0)
				classes.push(newclasses[i]);
		}
		this.className = classes.join(' ');
		return this;
	}
}); // }}}

// Remove a class from an element. Keep all other existing classes. Return the element for inline chaining.
Object.defineProperty(Object.prototype, 'RemoveClass', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(className) {
		if (!className)
			return this;
		var classes = this.className.split(' ');
		var oldclasses = className.split(' ');
		for (var i = 0; i < oldclasses.length; ++i) {
			var pos = classes.indexOf(oldclasses[i]);
			if (pos >= 0)
				classes.splice(pos, 1);
		}
		this.className = classes.join(' ');
		return this;
	}
}); // }}}

// Check if an element has a given class.
Object.defineProperty(Object.prototype, 'HaveClass', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(className) {
		if (!className)
			return true;
		var classes = this.className.split(' ');
		for (var i = 0; i < classes.length; ++i) {
			var pos = classes.indexOf(className);
			if (pos >= 0)
				return true;
		}
		return false;
	}
}); // }}}

// Add event listener. Return the object for inline chaining.
Object.defineProperty(Object.prototype, 'AddEvent', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(name, impl, capture) {
		this.addEventListener(name, impl, !!capture);
		return this;
	}
}); // }}}

// Remove event listener. Arguments should be identical to previous ones for AddEvent. Return the object for inline chaining.
Object.defineProperty(Object.prototype, 'RemoveEvent', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(name, impl) {
		this.removeEventListener(name, impl, false);
		return this;
	}
}); // }}}

// Compute offset of object from page origin.
Object.defineProperty(Object.prototype, 'Offset', { // {{{
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(e) {
		if (this.offsetParent)
			return this.offsetParent.Offset({pageX: e.pageX - this.offsetLeft, pageY: e.pageY - this.offsetTop});
		return [e.pageX - this.offsetLeft, e.pageY - this.offsetTop];
	}
}); // }}}

// }}}

// Build dictionary for cookies.
var cookie = function() { // {{{
	var ret = {};
	var data = document.cookie.split(';');
	for (var c = 0; c < data.length; ++c) {
		var m = data[c].match(/^(.*?)=(.*)$/);
		if (m === null)
			continue;
		ret[m[1].trim()] = m[2].trim();
	}
	return ret;
}(); // }}}

// Set a cookie to a (new) value. Set to null to discard it. SameSite defaults to 'Strict'.
function SetCookie(key, value, SameSite) { // {{{
	if (SameSite === undefined)
		SameSite = 'Strict';
	if (value === null) {
		delete cookie[key];
		document.cookie = key + '=; SameSite=' + SameSite + '; expires=Thu, 01 Jan 1970 00:00:01 GMT';
	}
	else {
		document.cookie = key + '=' + encodeURIComponent(value) + '; SameSite=' + SameSite;
	}
} // }}}

// Build dictionary for query string.
var search = function() { // {{{
	// search[key] is the first given value for each key.
	// search[''][key] is an array of all given values.
	var ret = {'': {}};
	var add = function(key, value) {
		key = decodeURIComponent(key);
		value = decodeURIComponent(value);
		if (ret[''][key] === undefined) {
			ret[''][key] = [value];
			ret[key] = value;
		}
		else
			ret[''][key].push(value);
	};
	var s = document.location.search;
	if (s == '')
		return ret;
	s = s.substr(1).split('&');
	for (var i = 0; i < s.length; ++i) {
		var pos = s[i].indexOf('=');
		if (pos == -1)
			add(s[i], null);
		else
			add(s[i].substr(0, pos), s[i].substr(pos + 1));
	}
	return ret;
}(); // }}}

// vim: set foldmethod=marker :
