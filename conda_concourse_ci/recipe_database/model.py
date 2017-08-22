from sqlalchemy import Table, Column, Integer, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

association_table = Table('association', Base.metadata,
    Column('recipe_id', Integer, ForeignKey('recipe.id')),
    Column('build_id', Integer, ForeignKey('build.id')),
    Column('run_id', Integer, ForeignKey('run.id')),
    Column('output_id', Integer, ForeignKey('outputs.id')),
)


class Recipe(Base):
    __tablename__ = 'recipe'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    version = Column(String)
    build_string = Column(String)
    path = Column(String)
    origin_repo = Column(String)
    origin_branch = Column(String)
    commit_id = Column(String)
    build_deps = relationship(
        "BuildDependency",
        secondary=association_table,
        back_populates="recipes")
    run_deps = relationship(
        "RunDependency",
        secondary=association_table,
        back_populates="recipes")
    outputs = relationship(
        "Output",
        secondary=association_table,
        back_populates="recipes")


class BuildDependency(Base):
    __tablename__ = 'build'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    constraint = Column(String)
    recipes = relationship(
        "Recipe",
        secondary=association_table,
        back_populates="build_deps")


class RunDependency(Base):
    __tablename__ = 'run'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    constraint = Column(String)
    recipes = relationship(
        "Recipe",
        secondary=association_table,
        back_populates="run_deps")


class Output(Base):
    __tablename__ = 'outputs'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    version = Column(String)
    recipes = relationship(
        "Recipe",
        secondary=association_table,
        back_populates="outputs")
