from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nba_id = Column(Integer, unique=True, nullable=False)
    name = Column(String, nullable=False)
    team = Column(String, nullable=False)
    position = Column(String, nullable=False)
    salary = Column(Integer, default=0)
    avg_minutes = Column(Float, default=0.0)
    is_usual_starter = Column(Boolean, default=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    game_logs = relationship("GameLog", back_populates="player")
    projections = relationship("Projection", back_populates="player")

    __table_args__ = (Index("ix_players_team_position", "team", "position"),)


class GameLog(Base):
    __tablename__ = "game_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_date = Column(Date, nullable=False)
    opponent = Column(String, nullable=False)
    minutes = Column(Float, default=0.0)
    pts = Column(Integer, default=0)
    reb = Column(Integer, default=0)
    ast = Column(Integer, default=0)
    stl = Column(Integer, default=0)
    blk = Column(Integer, default=0)
    tov = Column(Integer, default=0)
    three_pm = Column(Integer, default=0)
    started = Column(Boolean, default=False)
    dk_fp = Column(Float, default=0.0)

    player = relationship("Player", back_populates="game_logs")

    __table_args__ = (
        UniqueConstraint("player_id", "game_date", name="uq_player_game"),
        Index("ix_gamelogs_player_date", "player_id", "game_date"),
        Index("ix_gamelogs_opponent", "opponent", "game_date"),
    )


class TeamDefense(Base):
    __tablename__ = "team_defense"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team = Column(String, nullable=False)
    position = Column(String, nullable=False)
    dk_fp_allowed_avg = Column(Float, default=0.0)
    rank = Column(Integer, default=0)
    games_sampled = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("team", "position", name="uq_team_position_defense"),
    )


class InjuryReport(Base):
    __tablename__ = "injury_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player_name = Column(String, nullable=False)
    team = Column(String, nullable=False)
    position = Column(String, nullable=False)
    status = Column(String, nullable=False)  # Out, Doubtful, Questionable, Probable, GTD
    details = Column(String, default="")
    last_updated = Column(DateTime, default=datetime.utcnow)


class StartingLineup(Base):
    __tablename__ = "starting_lineups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team = Column(String, nullable=False)
    game_date = Column(Date, nullable=False)
    opponent = Column(String, nullable=False)
    pg = Column(String, default="")
    sg = Column(String, default="")
    sf = Column(String, default="")
    pf = Column(String, default="")
    c = Column(String, default="")
    confirmed = Column(Boolean, default=False)
    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("team", "game_date", name="uq_team_lineup_date"),
    )


class SpotStart(Base):
    __tablename__ = "spot_starts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player_name = Column(String, nullable=False)
    team = Column(String, nullable=False)
    position = Column(String, nullable=False)
    game_date = Column(Date, nullable=False)
    replacing_player = Column(String, default="")
    salary = Column(Integer, default=0)
    projected_minutes = Column(Float, default=0.0)
    historical_spot_avg_fp = Column(Float, default=0.0)
    spot_start_count = Column(Integer, default=0)
    value_score = Column(Float, default=0.0)
    confidence = Column(String, default="Expected")  # Confirmed, Expected, Probable
    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("player_id", "game_date", name="uq_spot_start_player_date"),
    )


class Projection(Base):
    __tablename__ = "projections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player_name = Column(String, nullable=False)
    team = Column(String, nullable=False)
    position = Column(String, nullable=False)
    opponent = Column(String, default="")
    salary = Column(Integer, default=0)
    projected_fp = Column(Float, default=0.0)
    dvp_score = Column(Float, default=0.0)
    dvp_grade = Column(String, default="C")  # A, B, C, D, F
    depth_score = Column(Float, default=0.0)
    injury_boost = Column(Float, default=0.0)
    spot_start_boost = Column(Float, default=0.0)
    ownership_pct = Column(Float, default=0.0)
    value_score = Column(Float, default=0.0)
    fp_per_dollar = Column(Float, default=0.0)
    is_spot_starter = Column(Boolean, default=False)
    is_confirmed_starter = Column(Boolean, default=False)
    minutes_projection = Column(Float, default=0.0)
    injury_status = Column(String, default="")  # "", "GTD", "Probable", "Out", "Doubtful"
    last_updated = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player", back_populates="projections")

    __table_args__ = (
        UniqueConstraint("player_id", name="uq_projection_player"),
        Index("ix_projections_position", "position"),
    )
