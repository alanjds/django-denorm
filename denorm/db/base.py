from django.db import (
    connection,
    connections,
    models,
    transaction,
)
from ..helpers import remote_field_model


class RandomBigInt(object):
    def sql(self):
        raise NotImplementedError


class TriggerNestedSelect:
    def __init__(self, table, columns, **kwargs):
        self.table = table
        self.columns = ", ".join(columns)
        self.kwargs = kwargs

    def sql(self):
        raise NotImplementedError


class TriggerAction(object):
    def __init__(self):
        pass

    def sql(self):
        pass


class TriggerActionInsert(TriggerAction):
    def __init__(self, model, columns, values):
        self.model = model
        self.columns = columns
        self.values = values

    def sql(self):
        raise NotImplementedError


class TriggerActionUpdate(TriggerAction):
    def __init__(self, model, columns, values, where):
        self.model = model
        self.columns = columns
        self.where = where

        self.values = []
        for value in values:
            if hasattr(value, 'sql'):
                self.values.append(value.sql())
            else:
                self.values.append(value)

    def sql(self):
        raise NotImplementedError


def get_fields_with_model(model, meta):
    try:
        return [
            (f, f.model if f.model != model else None)
            for f in meta.get_fields()
            if not f.is_relation
                or f.one_to_one
                or (f.many_to_one and f.related_model)
        ]
    except AttributeError:
        return meta.get_fields_with_model()

class Trigger(object):

    def __init__(self, subject, time, event, actions, content_type, using=None, skip=None):
        self.subject = subject
        self.time = time
        self.event = event
        self.content_type = content_type
        self.content_type_field = None
        self.actions = []
        self.append(actions)
        self.using = using

        if self.using:
            self.connection = connections[self.using]
        else:
            self.connection = connection

        try:
            from django.contrib.contenttypes.fields import GenericRelation
        except ImportError:
            from django.contrib.contenttypes.generic import GenericRelation

        if isinstance(subject, models.ManyToManyField):
            self.model = None
            self.db_table = subject.m2m_db_table()
            self.fields = [(subject.m2m_column_name(), ''), (subject.m2m_reverse_name(), '')]

        elif isinstance(subject, GenericRelation):
            self.model = None
            self.db_table = remote_field_model(subject)._meta.db_table
            self.fields = [(k.attname, k.db_type(connection=self.connection)) for k, v in get_fields_with_model(remote_field_model(subject), remote_field_model(subject)._meta) if not v]
            self.content_type_field = subject.content_type_field_name + '_id'

        elif isinstance(subject, models.ForeignKey):
            self.model = subject.model
            self.db_table = self.model._meta.db_table
            skip = skip or () + getattr(self.model, 'denorm_always_skip', ())
            self.fields = [(k.attname, k.db_type(connection=self.connection)) for k, v in get_fields_with_model(subject.model, self.model._meta) if not v and k.attname not in skip]

        elif hasattr(subject, "_meta"):
            self.model = subject
            self.db_table = self.model._meta.db_table
            # FIXME: need to check get_parent_list and add triggers to those
            # The below will only check the fields on *this* model, not parents
            skip = skip or () + getattr(self.model, 'denorm_always_skip', ())
            self.fields = []
            try:
                from django.db.models.fields.related import ForeignObjectRel
            except:
                from django.db.models.related import RelatedObject as ForeignObjectRel
            for k, v in get_fields_with_model(subject, self.model._meta):
                if isinstance(k, ForeignObjectRel):
                    pass
                else:
                    if not v and k.attname not in skip:
                        self.fields.append((k.attname, k.db_type(connection=self.connection)))

        else:
            raise NotImplementedError

    def append(self, actions):
        if not isinstance(actions, list):
            actions = [actions]

        for action in actions:
            self.actions.append(action)

    def name(self):
        return "_".join([
            "denorm",
            self.time,
            "row",
            self.event,
            "on",
            self.db_table
        ])

    def sql(self):
        raise NotImplementedError


class TriggerSet(object):
    def __init__(self, using=None):
        self.using = using
        self.triggers = {}
        if self.using:
            self.connection = connections[self.using]
        else:
            self.connection = connection

    def cursor(self):
        return self.connection.cursor()

    def append(self, triggers):
        if not isinstance(triggers, list):
            triggers = [triggers]

        for trigger in triggers:
            name = trigger.name()
            if name in self.triggers:
                self.triggers[name].append(trigger.actions)
            else:
                self.triggers[name] = trigger

    def installed_triggers(self):
        """returns a list of (trigger_name, table_name) pairs"""
        raise NotImplementedError

    def drop_trigger(self, trigger_name, table_name):
        """executes the command to drop the given trigger"""
        raise NotImplementedError

    def drop_unneeded_atomic(self):
        needed_triggers = self.triggers.keys()
        for name, table_name in self.installed_triggers():
            if name in needed_triggers:
                continue
            print 'Dropping a trigger on %s' % table_name
            self.drop_trigger(name, table_name)

    def drop_unneeded(self):
        try:
            with transaction.atomic():
                self.drop_unneeded_atomic()
        except AttributeError:
            self.drop_unneeded_atomic()
            transaction.commit_unless_managed(using=self.using)

    def drop_atomic(self):
        for trigger_name, table_name in self.installed_triggers():
            self.drop_trigger(trigger_name, table_name)

    def drop(self):
        try:
            with transaction.atomic():
                self.drop_atomic()
        except AttributeError:
            self.drop_atomic()
            transaction.commit_unless_managed(using=self.using)

    def install_atomic(self):
        cursor = self.cursor()
        installed_triggers = self.installed_triggers()
        if len(installed_triggers) > 0:
            installed_triggers = zip(*installed_triggers)[0]  # get just the names
        for name, trigger in self.triggers.items():
            if name in installed_triggers:
                continue
            sql, args = trigger.sql()
            cursor.execute(sql, args)
            yield trigger

    def install(self):
        try:
            with transaction.atomic():
                ret = list(self.install_atomic())
        except AttributeError:
            ret = list(self.install_atomic())
            transaction.commit_unless_managed(using=self.using)
        return ret
