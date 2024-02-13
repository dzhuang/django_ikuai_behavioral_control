/*global Calendar, findPosX, findPosY, get_format, gettext, gettext_noop, interpolate, ngettext, quickElement*/
// Inserts shortcut buttons after all of the following:
//     <input type="text" class="vDateField">
//     <input type="text" class="vTimeField">
'use strict';
{
    const DateTimeShortcuts = {
        calendarDay: [],
        calendarInputs: [],
        clockInputs: [],
        clockEndInputs: [],
        minutesInputs: [],
        minutesOptions: {
            default_: [
                [gettext_noop('5 minutes'), 5],
                [gettext_noop('15 minutes'), 15],
                [gettext_noop('30 minutes'), 30],
                [gettext_noop('45 minutes'), 45],
                [gettext_noop('1 hour'), 60],
                [gettext_noop('90 minutes'), 90],
                [gettext_noop('2 hours'), 120],
                [gettext_noop('3 hours'), 180],
                [gettext_noop('4 hours'), 240],
                [gettext_noop('5 hours'), 300],
                [gettext_noop('6 hours'), 360],
            ]
        },
        dismissMinuteFunc: [],

        dismissClockFunc: [],
        minutesDivName: 'miniutebox',
        minutesLinkName: 'miniutelink',
        clockDivName: 'clockbox', // name of clock <div> that gets toggled
        clockLinkName: 'clocklink', // name of the link that is used to toggle
        shortCutsClass: 'datetimeshortcuts', // class of the clock and cal shortcuts
        timezoneWarningClass: 'timezonewarning', // class of the warning for timezone mismatch
        timezoneOffset: 0,
        init: function() {
            const serverOffset = document.body.dataset.adminUtcOffset;
            if (serverOffset) {
                const localOffset = new Date().getTimezoneOffset() * -60;
                DateTimeShortcuts.timezoneOffset = localOffset - serverOffset;
            }

            for (const inp of document.getElementsByTagName('input')) {
                if ((inp.type === 'time' || inp.type === 'text') && inp.classList.contains('vTimeField')) {
                    DateTimeShortcuts.addClock(inp);
                    DateTimeShortcuts.addTimezoneWarning(inp);
                }
                else if ((inp.type === 'time' || inp.type === 'text') && inp.classList.contains('vTimeEndField')) {
                    DateTimeShortcuts.addClockEnd(inp);
                    DateTimeShortcuts.addTimezoneWarning(inp);
                }
            }
            for (const sel of document.getElementsByTagName('select')) {
                if (sel.classList.contains('vSelectDay')) {
                    DateTimeShortcuts.addCalendar(sel);
                }
                else if (sel.classList.contains('vMinutesField')) {
                    DateTimeShortcuts.addMinutes(sel);
                }
            }
        },
        // Return the current time while accounting for the server timezone.
        now: function() {
            const serverOffset = document.body.dataset.adminUtcOffset;
            if (serverOffset) {
                const localNow = new Date();
                const localOffset = localNow.getTimezoneOffset() * -60;
                localNow.setTime(localNow.getTime() + 1000 * (serverOffset - localOffset));
                return localNow;
            } else {
                return new Date();
            }
        },
        // Add a warning when the time zone in the browser and backend do not match.
        addTimezoneWarning: function(inp) {
            const warningClass = DateTimeShortcuts.timezoneWarningClass;
            let timezoneOffset = DateTimeShortcuts.timezoneOffset / 3600;

            // Only warn if there is a time zone mismatch.
            if (!timezoneOffset) {
                return;
            }

            // Check if warning is already there.
            if (inp.parentNode.querySelectorAll('.' + warningClass).length) {
                return;
            }

            let message;
            if (timezoneOffset > 0) {
                message = ngettext(
                    'Note: You are %s hour ahead of server time.',
                    'Note: You are %s hours ahead of server time.',
                    timezoneOffset
                );
            }
            else {
                timezoneOffset *= -1;
                message = ngettext(
                    'Note: You are %s hour behind server time.',
                    'Note: You are %s hours behind server time.',
                    timezoneOffset
                );
            }
            message = interpolate(message, [timezoneOffset]);

            const warning = document.createElement('span');
            warning.className = warningClass;
            warning.textContent = message;
            inp.parentNode.appendChild(document.createElement('br'));
            inp.parentNode.appendChild(warning);
        },
        addMinutes: function (sel) {
            const num = DateTimeShortcuts.minutesInputs.length;
            DateTimeShortcuts.minutesInputs[num] = sel;

            DateTimeShortcuts.minutesInputs[num].addEventListener('change', function(e){
                DateTimeShortcuts.updateEndTime(num);
            })

            DateTimeShortcuts.dismissMinuteFunc[num] = function() { DateTimeShortcuts.dismissMinutes(num); return true; };

            // Shortcut links (clock icon and "15 minutes" link)
            const shortcuts_span = document.createElement('span');
            shortcuts_span.className = DateTimeShortcuts.shortCutsClass;
            sel.parentNode.insertBefore(shortcuts_span, sel.nextSibling);
            const m15_link = document.createElement('a');
            m15_link.href = "#";
            m15_link.textContent = gettext('15 minutes');
            m15_link.addEventListener('click', function(e) {
                e.preventDefault();
                DateTimeShortcuts.handleMinutesQuicklink(num, 15);
            });
            const minutes_link = document.createElement('a');
            minutes_link.href = '#';
            minutes_link.id = DateTimeShortcuts.minutesLinkName + num;
            minutes_link.addEventListener('click', function(e) {
                e.preventDefault();
                // avoid triggering the document click handler to dismiss the clock
                e.stopPropagation();
                DateTimeShortcuts.openMinutes(num);
            });

            quickElement(
                'span', minutes_link, '',
                'class', 'clock-icon',
                'title', gettext('Choose a Time')
            );
            shortcuts_span.appendChild(document.createTextNode('\u00A0'));
            shortcuts_span.appendChild(m15_link);
            shortcuts_span.appendChild(document.createTextNode('\u00A0|\u00A0'));
            shortcuts_span.appendChild(minutes_link);

            // Create clock link div
            //
            // Markup looks like:
            // <div id="clockbox1" class="clockbox module">
            //     <h2>Choose a time</h2>
            //     <ul class="timelist">
            //         <li><a href="#">Now</a></li>
            //         <li><a href="#">Midnight</a></li>
            //         <li><a href="#">6 a.m.</a></li>
            //         <li><a href="#">Noon</a></li>
            //         <li><a href="#">6 p.m.</a></li>
            //     </ul>
            //     <p class="calendar-cancel"><a href="#">Cancel</a></p>
            // </div>

            const minute_box = document.createElement('div');
            minute_box.style.display = 'none';
            minute_box.style.position = 'absolute';
            minute_box.className = 'minutebox module';
            minute_box.id = DateTimeShortcuts.minutesDivName + num;
            document.body.appendChild(minute_box);
            minute_box.addEventListener('click', function(e) { e.stopPropagation(); });

            quickElement('h4', minute_box, gettext('Choose a time'));
            const minute_list = quickElement('ul', minute_box);
            minute_list.className = 'minutelist';
            // The list of choices can be overridden in JavaScript like this:
            // DateTimeShortcuts.minutesOptions.name = [['3 a.m.', 3]];
            // where name is the name attribute of the <input>.
            const name = typeof DateTimeShortcuts.minutesOptions[sel.name] === 'undefined' ? 'default_' : sel.name;
            DateTimeShortcuts.minutesOptions[name].forEach(function(element) {
                const time_link = quickElement('a', quickElement('li', minute_list), gettext(element[0]), 'href', '#');
                time_link.addEventListener('click', function(e) {
                    e.preventDefault();
                    DateTimeShortcuts.handleMinutesQuicklink(num, element[1]);
                });
            });

            const cancel_p = quickElement('p', minute_box);
            cancel_p.className = 'minutes-cancel';
            const cancel_link = quickElement('a', cancel_p, gettext('Cancel'), 'href', '#');
            cancel_link.addEventListener('click', function(e) {
                e.preventDefault();
                DateTimeShortcuts.dismissMinutes(num);
            });

            document.addEventListener('keyup', function(event) {
                if (event.which === 27) {
                    // ESC key closes popup
                    DateTimeShortcuts.dismissMinutes(num);
                    event.preventDefault();
                }
            });

        },
        openMinutes: function(num) {
            const minutes_box = document.getElementById(DateTimeShortcuts.minutesDivName + num);
            const minutes_link = document.getElementById(DateTimeShortcuts.minutesLinkName + num);

            // Recalculate the clockbox position
            // is it left-to-right or right-to-left layout ?
            if (window.getComputedStyle(document.body).direction !== 'rtl') {
                minutes_box.style.left = findPosX(minutes_link) + 17 + 'px';
            }
            else {
                // since style's width is in em, it'd be tough to calculate
                // px value of it. let's use an estimated px for now
                minutes_box.style.left = findPosX(minutes_link) - 110 + 'px';
            }
            minutes_box.style.top = Math.max(0, findPosY(minutes_link) - 30) + 'px';

            // Show the clock box
            minutes_box.style.display = 'block';

            // dismiss the widget when click
            document.addEventListener('click', DateTimeShortcuts.dismissMinuteFunc[num]);
        },
        addClockEnd: function(inp) {
            const num = DateTimeShortcuts.clockEndInputs.length;
            DateTimeShortcuts.clockEndInputs[num] = inp;
        },
        // Add clock widget to a given field
        addClock: function(inp) {
            const num = DateTimeShortcuts.clockInputs.length;
            DateTimeShortcuts.clockInputs[num] = inp;

            DateTimeShortcuts.clockInputs[num].addEventListener('change', function(e){
                DateTimeShortcuts.updateEndTime(num);
            })

            // Shortcut links (clock icon and "Now" link)
            const shortcuts_span = document.createElement('span');
            shortcuts_span.className = DateTimeShortcuts.shortCutsClass;
            inp.parentNode.insertBefore(shortcuts_span, inp.nextSibling);
            const now_link = document.createElement('a');
            now_link.href = "#";
            now_link.textContent = gettext('Now');
            now_link.addEventListener('click', function(e) {
                e.preventDefault();
                DateTimeShortcuts.handleClockQuicklink(num, -1);
            });
            shortcuts_span.appendChild(document.createTextNode('\u00A0'));
            shortcuts_span.appendChild(now_link);
        },
        dismissMinutes: function(num) {
            document.getElementById(DateTimeShortcuts.minutesDivName + num).style.display = 'none';
            document.removeEventListener('click', DateTimeShortcuts.dismissMinuteFunc[num]);
        },
        handleMinutesQuicklink: function(num, val) {
            DateTimeShortcuts.minutesInputs[num].value = val;
            // DateTimeShortcuts.minutesInputs[num].focus();
            DateTimeShortcuts.dismissMinutes(num);
            DateTimeShortcuts.updateEndTime(num);
        },

        updateEndTime: function (num){
            const d = DateTimeShortcuts.now();
            const timeStr = d.strftime("%Y-%m-%d") + " " + DateTimeShortcuts.clockInputs[num].value;
            let oldDate, newDate, currentTime, newTime;
            currentTime = new Date(timeStr);
            newTime = new Date(timeStr);
            oldDate = currentTime.getDate();

            const minutes = DateTimeShortcuts.minutesInputs[num].value;
            newTime.setTime(currentTime.getTime() + (minutes * 60 * 1000));
            newDate = newTime.getDate();

            if (newDate > oldDate) {
                newTime = "23:59"
            }
            else{
                newTime = newTime.strftime(get_format('TIME_INPUT_FORMATS')[0])
            }
            DateTimeShortcuts.clockEndInputs[num].value = newTime
        },

        handleClockQuicklink: function(num, val) {
            let d;
            if (val === -1) {
                d = DateTimeShortcuts.now();
            }
            else {
                d = new Date(1970, 1, 1, val, 0, 0, 0);
            }
            DateTimeShortcuts.clockInputs[num].value = d.strftime(get_format('TIME_INPUT_FORMATS')[0]);
            DateTimeShortcuts.clockInputs[num].focus();
            DateTimeShortcuts.updateEndTime(num);
        },
        // Add calendar widget to a given field.
        addCalendar: function(inp) {
            const num = DateTimeShortcuts.calendarDay.length;

            DateTimeShortcuts.calendarInputs[num] = inp;

            // Shortcut links (calendar icon and "Today" link)
            const shortcuts_span = document.createElement('span');
            shortcuts_span.className = DateTimeShortcuts.shortCutsClass;
            inp.parentNode.insertBefore(shortcuts_span, inp.nextSibling);
            const today_link = document.createElement('a');
            today_link.href = '#';
            today_link.appendChild(document.createTextNode(gettext('Today')));
            today_link.addEventListener('click', function(e) {
                e.preventDefault();
                DateTimeShortcuts.handleCalendarQuickLink(num, 0);
            });
            const tomorrow_link = document.createElement('a');
            tomorrow_link.href = '#';
            tomorrow_link.appendChild(document.createTextNode(gettext('Tomorrow')));
            tomorrow_link.addEventListener('click', function(e) {
                e.preventDefault();
                DateTimeShortcuts.handleCalendarQuickLink(num, 1);
            });

            shortcuts_span.appendChild(document.createTextNode('\u00A0'));
            shortcuts_span.appendChild(today_link);
            shortcuts_span.appendChild(document.createTextNode('\u00A0|\u00A0'));
            shortcuts_span.appendChild(tomorrow_link);

        },
        handleCalendarQuickLink: function(num, offset) {
            const d = DateTimeShortcuts.now();
            d.setDate(d.getDate() + offset);

            const dObj = {
                1: "mon",
                2: "tue",
                3: "wed",
                4: "thu",
                5: "fri",
                6: "sat",
                0: "sun"
            }
            DateTimeShortcuts.calendarInputs[num].value = dObj[d.getDay()];
        }
    };

    window.addEventListener('load', DateTimeShortcuts.init);
    window.DateTimeShortcuts = DateTimeShortcuts;
}
