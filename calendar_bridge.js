// JavaScript for Automation, executed by macOS osascript.
// Booking-derived values arrive as JSON data, never as generated script code.
function calendarIdentifier(calendar) {
    // Calendar's id/uid property getters fail on some macOS versions.
    // The returned object specifier already contains its byId identifier.
    var specifier = Automation.getDisplayString(calendar);
    var match = /\.calendars\.byId\(("(?:[^"\\]|\\.)*")\)$/.exec(specifier);
    if (!match) {
        throw new Error('Cannot resolve calendar identifier from its object reference: ' + specifier);
    }
    return JSON.parse(match[1]);
}

function run(argv) {
    var request = JSON.parse(argv[0]);
    var app = Application('Calendar');
    if (request.action === 'list') {
        return JSON.stringify({calendars: app.calendars().map(function (calendar) {
            var name;
            var stage = 'reading its name';
            try {
                name = calendar.name();
                stage = 'resolving its identifier';
                var identifier = calendarIdentifier(calendar);
                stage = 'reading its writable property';
                var writable = calendar.writable();
                return {id: identifier, name: name, writable: writable};
            } catch (error) {
                throw new Error('Calendar ' + (name || '(name unavailable)') + ', ' + stage + ': ' + error.message);
            }
        })});
    }
    var calendar = app.calendars.byId(request.calendar_id);
    if (!calendar.exists()) throw new Error('The selected calendar no longer exists. Reload calendars.');
    if (!calendar.writable()) throw new Error('The selected calendar is read-only.');
    var marker = '[ticket-to-calendar:' + request.request_id + ']';
    // Repeated requests for the same reviewed event return its existing UID.
    var matches = calendar.events.whose({description: {_contains: marker}})();
    if (matches.length) {
        return JSON.stringify({status: 'already_exists', event_id: matches[0].uid(),
            calendar_id: request.calendar_id, calendar_name: calendar.name()});
    }
    var event = app.Event({summary: request.title, startDate: new Date(request.start),
        endDate: new Date(request.end), location: request.location,
        description: request.notes + '\n\n' + marker, alldayEvent: false});
    calendar.events.push(event);
    return JSON.stringify({status: 'created', event_id: event.uid(),
        calendar_id: request.calendar_id, calendar_name: calendar.name()});
}
