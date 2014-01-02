from __future__ import print_function, division, absolute_import

import pytest
import os

from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base

import multialchemy

import sqlalchemy

# Whew, this test fixtures dependency thing is fun.  Hope I didn't go overboard.
@pytest.fixture(scope="module")
def engine():
    try:
        os.remove("multialchemy_test.db")
    except OSError:
        pass

    engine = create_engine("sqlite:///multialchemy_test.db")
    return engine


@pytest.fixture(scope="module")
def models(engine):
    Base = declarative_base(cls=multialchemy.Base)
    #Base = declarative_base()

    @Base.tenant_class
    class Tenant(Base):
        __tablename__ = 'tenants'
        __multitenant__ = False

        id = Column(Integer, primary_key=True)
        name = Column(String(200))

    class User(Base):
        __tablename__ = 'users'
        __multitenant__ = False

        id = Column(Integer, primary_key=True)
        name = Column(String(200))

    class Post(Base):
        __tablename__ = 'posts'

        id = Column(Integer, primary_key=True)
        title = Column(String(200))
        author_id = Column(Integer, ForeignKey('users.id'))
        author = relationship(User, backref='posts')
        tenant_id = Column(Integer, ForeignKey('tenants.id'))

    class foo(object):
        pass

    models = foo()
    models.Tenant = Tenant
    models.User = User
    models.Post = Post
    Base.metadata.create_all(engine)
    engine.execute("INSERT INTO tenants (name) VALUES ('multialchemy')")
    engine.execute("INSERT INTO users (name) VALUES ('mwhite')")
    engine.execute("INSERT INTO posts (title, author_id, tenant_id)"
            "VALUES ('woo!', 1, 1)")
    return models


@pytest.fixture(scope="module")
def TenantSession(engine, models):
    return sessionmaker(bind=engine, class_=multialchemy.TenantSession)
    #return sessionmaker(bind=engine)


@pytest.fixture(scope="function")
def session(TenantSession, models):
    session = TenantSession()
    tenant = session.query(models.Tenant, safe=False).first()
    session.tenant = tenant
    return session


def test_non_multitenant_model_has_no_tenant(models):
    assert 'tenant_id' not in models.User.__table__.c


def test_multitenant_model_has_tenant(models):
    assert 'tenant_id' in models.Post.__table__.c
    fk = models.Post.__table__.c['tenant_id'].foreign_keys.pop()
    assert fk.column == models.Tenant.__table__.c['id']


def test_multitenant_query_enforces_tenant(models, session):
    sql = str(session.query(models.Post))
    assert 'posts.tenant_id =' in sql


def test_join_enforces_tenant(models, session):
    sql = str(session.query(models.User).join(models.Post))
    print(sql)
    assert 'posts.tenant_id = ' in sql
    assert 'JOIN' in sql


def test_keeps_existing_criterion(models, session):
    sql = str(session.query(models.User).filter_by(name='Bob').\
            join(models.User.posts))
    assert 'users.name =' in sql


def test_unsafe_query_doesnt_enforce_tenant(models, session):
    sql = str(session.query(models.Post, safe=False))
    assert 'posts.tenant_id =' not in sql


def test_non_multitenant_query_doesnt_enforce_tenant(models, session):
    sql = str(session.query(models.User))
    assert 'tenant_id' not in sql


def test_new_instance_gets_tenant_id_when_added(models, session):
    post = models.Post(title='Foo!', author_id=1)
    session.add(post)
    assert post.tenant_id == session.tenant.id


def test_cant_add_instance_with_incorrect_tenant(models, session):
    post = models.Post(title='Bar!', author_id=1, tenant_id=2)
    with pytest.raises(multialchemy.TenantConflict):
        session.add(post)


def test_cant_change_tenant_id(models, session):
    post = models.Post(title='Bar!', author_id=1, tenant_id=1)
    session.add(post)
    session.commit()
    post.tenant_id = 2
    with pytest.raises(multialchemy.TenantConflict):
        session.add(post)
    with pytest.raises(multialchemy.TenantConflict):
        session.delete(post)


def test_can_remove_tenant_from_session(models, session):
    session.tenant = None
    with pytest.raises(multialchemy.UnboundTenantError):
        post = models.Post(title='Whoops!', author_id=1, tenant_id=1)
        session.add(post)

    with pytest.raises(multialchemy.UnboundTenantError):
        session.query(models.Post).first()


def test_delete_instance(models, session):
    post = session.query(models.Post).first()
    session.delete(post)
