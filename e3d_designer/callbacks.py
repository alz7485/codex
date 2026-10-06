"""Keep one editable definition for gadgets sharing a callback."""


def callback_body(form, gadget):
    if gadget.callback.lower() == 'default':
        return form.default_body or next((g.body for g in form.gadgets
                                         if g.callback.lower() == 'default' and g.body), '')
    return gadget.body


def join_callback(form, gadget, previous_name):
    if gadget.callback.lower() == previous_name.lower():
        return
    if gadget.callback.lower() == 'default':
        gadget.body = ''
    elif gadget.callback:
        other = next((g for g in form.gadgets if g is not gadget
                      and g.callback.lower() == gadget.callback.lower()), None)
        if other is not None:
            gadget.body = other.body


def set_callback_body(form, gadget, body):
    if gadget.callback.lower() == 'default':
        form.default_body = body
        for other in form.gadgets:
            if other.callback.lower() == 'default':
                other.body = ''
    elif gadget.callback:
        for other in form.gadgets:
            if other.callback.lower() == gadget.callback.lower():
                other.body = body
    else:
        gadget.body = body
