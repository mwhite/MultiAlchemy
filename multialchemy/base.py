from sqlalchemy import inspection, event, Column, Integer, ForeignKey
from sqlalchemy.orm import session, query
from sqlalchemy.sql import expression
from sqlalchemy.ext.declarative import declared_attr
import sqlalchemy

__all__ = [
    'Base',
    'TenantSession',
    'TenantConflict',
    'UnboundTenantError'
]

SQLA_VERSION_8 = sqlalchemy.__version__.startswith('0.8')


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

        return Column(
                Integer, ForeignKey("%s.id" % cls._tenant_cls.__tablename__),
                index=True)


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
    def __init__(self, *args, **kwargs):
        self._safe = kwargs.pop('safe', True)
        super(TenantQuery, self).__init__(*args, **kwargs)

    @property
    def _from_obj(self):
        # we only do the multitenant processing on accessing the _from_obj /
        # froms properties, rather than have a wrapper object, because it
        # wasn't possible to implement the right magic methods and still have
        # the wrapper object evaluate to the underlying sequence.
        # This approach is fine because adding a given criterion is idempotent.
        if getattr(self, '_from_obj_', None) is None:
            self._from_obj_ = ()
        for from_ in self._from_obj_:
            _process_from(from_, self)
        return self._from_obj_

    @_from_obj.setter
    def _from_obj(self, value):
        self._from_obj_ = value

    def _join_to_left(self, *args, **kwargs):

        right = args[1 if SQLA_VERSION_8 else 2]
        super(TenantQuery, self)._join_to_left(*args, **kwargs)

        _process_from(inspection.inspect(right).selectable, self)


class TenantQueryContext(query.QueryContext):
    @property
    def froms(self):
        if getattr(self, '_froms', None) is None:
            self._froms = []
        for from_ in self._froms:
            _process_from(from_, self.query, self)
        return self._froms

    @froms.setter
    def froms(self, value):
        self._froms = value

# monkey patch to avoid needing changes to SQLAlchemy
query.QueryContext = TenantQueryContext


def _process_from(from_, query, query_context=None):
    if not getattr(query, '_safe', None):
        return

    tenant_id_col = from_.c.get('tenant_id')
    if tenant_id_col is not None:
        if query.session.tenant is None:
            raise UnboundTenantError(
                "Tried to do a tenant-bound query in a tenantless context.")

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
