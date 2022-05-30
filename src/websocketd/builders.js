// vim: set foldmethod=marker :

function Create(name, className) {
	return document.createElement(name).AddClass(className);
}

Object.defineProperty(Object.prototype, 'Offset', {
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(e) {
		if (this.offsetParent)
			return this.offsetParent.Offset({pageX: e.pageX - this.offsetLeft, pageY: e.pageY - this.offsetTop});
		return [e.pageX - this.offsetLeft, e.pageY - this.offsetTop];
	}});

Object.defineProperty(Object.prototype, 'Add', {
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
	}});

Object.defineProperty(Object.prototype, 'AddElement', {
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(name, className) {
		var element = document.createElement(name);
		return this.Add(element, className);
	}});

Object.defineProperty(Object.prototype, 'AddText', {
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(text) {
		var t = document.createTextNode(text);
		this.Add(t);
		return this;
	}});

Object.defineProperty(Object.prototype, 'ClearAll', {
	enumerable: false,
	configurable: true,
	writable: true,
	value: function() {
		while (this.firstChild)
			this.removeChild(this.firstChild);
		return this;
	}});

Object.defineProperty(Object.prototype, 'AddClass', {
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
	}});

Object.defineProperty(Object.prototype, 'RemoveClass', {
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
	}});

Object.defineProperty(Object.prototype, 'HaveClass', {
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
	}});

Object.defineProperty(Object.prototype, 'AddEvent', {
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(name, impl) {
		this.addEventListener(name, impl, false);
		return this;
	}});

Object.defineProperty(Object.prototype, 'RemoveEvent', {
	enumerable: false,
	configurable: true,
	writable: true,
	value: function(name, impl) {
		this.removeEventListener(name, impl, false);
		return this;
	}});

var search = function() {
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
}();
