// vim: set foldmethod=marker :

function debug(msg) {
	// Don't use Add, because this should be callable from anywhere, including Add.
	var div = document.getElementById('debug');
	var p = document.createElement('p');
	div.appendChild(p);
	p.appendChild(document.createTextNode(msg));
}

function Create(name, className) {
	return document.createElement(name).AddClass(className);
}

Object.prototype.Offset = function(e) {
	if (this.offsetParent)
		return this.offsetParent.Offset({pageX: e.pageX - this.offsetLeft, pageY: e.pageY - this.offsetTop});
	return [e.pageX - this.offsetLeft, e.pageY - this.offsetTop];
};

Object.prototype.Add = function(object, className) {
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
};

Object.prototype.AddElement = function(name, className) {
	var element = document.createElement(name);
	return this.Add(element, className);
};

Object.prototype.AddText = function(text) {
	var t = document.createTextNode(text);
	this.Add(t);
	return this;
};

Object.prototype.ClearAll = function() {
	while (this.firstChild)
		this.removeChild(this.firstChild);
	return this;
};

Object.prototype.AddClass = function(className) {
	if (!className)
		return this;
	var classes = this.className.split(' ');
	var newclasses = className.split(' ');
	for (var i = 0; i < newclasses.length; ++i) {
		if (classes.indexOf(newclasses[i]) < 0)
			classes.push(newclasses[i]);
	}
	this.className = classes.join(' ');
	return this;
};

Object.prototype.RemoveClass = function(className) {
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
};

Object.prototype.AddEvent = function(name, impl) {
	this.addEventListener(name, impl, false);
	return this;
};
