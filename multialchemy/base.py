from sqlalchemy import inspection, event, Column, Integer, ForeignKey
from sqlalchemy.orm import session, query
from sqlalchemy.sql import expression
from sqlalchemy.ext.declarative import declared_attr

__all__ = [
    'Base',
    'TenantSession',
    'TenantConflict',
    'UnboundTenantError'
]


class UnboundTenantError(Exception):
    pass

class TenantConflict(Exception):
    pass


class Base(object):
    __multitenant__ = True
    __plural_tablename__ = None

    @classmethod
    def tenant_class(cls, tenant_cls):
        cls._tenant_cls = tenant_cls
        event.listen(tenant_cls, 'after_insert', after_tenant_insert)
        event.listen(tenant_cls, 'before_delete', before_tenant_delete)
        return tenant_cls

    @declared_attr
    def tenant_id(cls):
        if not cls.__multitenant__:
            return None

        return Column(Integer,
                ForeignKey("%s.id" % cls._tenant_cls.__tablename__))


    # abandoning this for now as it causes unexpected SQLAlchemy error
    #@declared_attr
    #def tenant(cls):
        #if not cls.__multitenant__:
            #return None

        #return relationship(
                #cls._tenant_cls, primaryjoin=(cls.tenant_id ==
                                              #cls._tenant_cls.id), 
                #backref=cls._tenant_cls.__tablename__)


def after_tenant_insert(mapper, connection, target):
    # create user
    # create views
    # revoke all on user
    pass

def before_tenant_delete(mapper, connection, target):
    # backup data?
    # drop views
    # drop user
    # drop data
    pass





class TenantSession(session.Session):
    def __init__(self, query_cls=None, *args, **kwargs):
        self.tenant = None

        query_cls = query_cls or TenantQuery

        super(TenantSession, self).__init__(
                query_cls=query_cls, *args, **kwargs)
        
    def query(self, *args, **kwargs):
        kwargs.setdefault('safe', True)
        return super(TenantSession, self).query(*args, **kwargs)

    def add(self, instance, *args, **kwargs):
        self.check_instance(instance)
        instance.tenant_id = self.tenant.id
        super(TenantSession, self).add(instance, *args, **kwargs)

    def delete(self, instance, *args, **kwargs):
        self.check_instance(instance)
        super(TenantSession, self).delete(instance, *args, **kwargs)

    def merge(self, instance, *args, **kwargs):
        self.check_instance(instance)
        super(TenantSession, self).merge(instance, *args, **kwargs)

    def check_instance(self, instance):
        if instance.__multitenant__ and self.tenant is None:
            raise UnboundTenantError(
                "Tried to do a tenant-safe operation in a tenantless context.")

        if instance.__multitenant__ and instance.tenant_id is not None and \
           instance.tenant_id != self.tenant.id:
            raise TenantConflict((
                "Tried to use a %r with tenant_id %r in a session with " +
                "tenant_id %r") % (
                    type(instance), instance.tenant_id, self.tenant.id))


class TenantQuery(query.Query):
    @property
    def _from_obj(self):
        if getattr(self, '_from_obj_', None) is None:
            self._from_obj_ = FromObjWrapper(())
            self._from_obj_.set_query(self)
        return self._from_obj_

    @_from_obj.setter
    def _from_obj(self, value):
        self._from_obj_ = FromObjWrapper(value)
        self._from_obj_.set_query(self)

    def __init__(self, *args, **kwargs):
        self._safe = kwargs.pop('safe', True)
        super(TenantQuery, self).__init__(*args, **kwargs)

    def _join_to_left(self, l_info, left, right, onclause, outerjoin):
        retval = super(TenantQuery, self)._join_to_left(
                l_info, left, right, onclause, outerjoin)

        _process_from(inspection.inspect(right).selectable, self)
        return retval


def _process_from(from_, query, query_context=None):
    if not query._safe:
        return

    tenant_id_col = from_.c.get('tenant_id')
    if tenant_id_col is not None:
        if query.session.tenant is None:
            raise UnboundTenantError(
                "Tried to do a tenant-bound query in a tenantless session.")

        # logic copied from orm.Query.filter, in order to be able to modify
        # the existing query in place
        criterion = expression._literal_as_text(
                tenant_id_col == query.session.tenant.id)
        criterion = query._adapt_clause(criterion, True, True)

        if query_context is None:
            if query._criterion is not None:
                query._criterion = query._criterion & criterion
            else:
                query._criterion = criterion
        else:
            if query_context.whereclause is not None:
                query_context.whereclause = (
                        query_context.whereclause & criterion)
            else:
                query_context.whereclause = criterion


class _FromsWrapper(object):
    """
    The QueryContext.froms instance attribute is replaced with an instance of
    this to ensure that any time a query selects from a multi-tenant table in a
    TenantSession, a criterion is added to the query to ensure that only rows
    owned by the correct tenant are included in the results.

    At the moment, removing elements or deleting QueryContext.froms does not
    remove associated criteria from the query.
    """
    def __init__(self, value):
        self.value = value

    def set_query(self, query, query_context=None):
        self.query = query
        self.query_context = query_context
        for from_ in self.value:
            self._process(from_)

    def __iadd__(self, value):
        self.extend(value)

    def extend(self, value):
        value = list(value)
        for from_ in value:
            self._process(from_)
        self.value.extend(value)

    def __add__(self, other):
        other = list(other)
        for from_ in other:
            _process_from(from_, self.query)
        return list(self.value) + other

    def _process(self, from_):
        _process_from(from_, self.query, self.query_context)
    
    # not used by SQLAlchemy
    #def append(self, from_):
        #self._process(from_)
        #self.value.append(from_)

    #def __setitem__(self, item, value):
        #self._process(value)
        #self.value[item] = value


# Subclassing tuple doesn't do anything here other than ensure that there isn't
# a type error when an actual tuple is added to an instance in SQLAlchemy.
class FromObjWrapper(_FromsWrapper, tuple):
    pass


# Subclassing list doesn't actually do anything here, except to fool
# SQLAlchemy's inspection API in order to keep things working the way they're
# supposed to.
class FromsWrapper(_FromsWrapper, list):
    pass


class TenantQueryContext(query.QueryContext):
    @property
    def froms(self):
        if getattr(self, '_froms', None) is None:
            self._froms = FromsWrapper([])
            self._froms.set_query(self.query, self)
        return self._froms

    @froms.setter
    def froms(self, value):
        if isinstance(value, FromsWrapper):
            self._froms = value
        else:
            self._froms = FromsWrapper(value or [])
            self._froms.set_query(self.query, self)

# monkey patch to avoid needing changes to SQLAlchemy
query.QueryContext = TenantQueryContext
